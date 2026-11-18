"""Entrypoint for the always-on worker process.

Polls every tracked, configured-platform streamer for live status; when one
goes live, starts recording, chat ingestion, highlight detection and
clipping for that session; notifies Discord for review; and republishes
approved clips through Post for Me. Run with:

    python -m streamclip.worker_main

Everything here is built from the modules the test suite already covers
(`platforms`, `recorder`, `detection`, `clipper`, `orchestrator`,
`discord_bot`, `publisher`) - this module's job is only to wire them
together against real settings/credentials and keep the process alive.
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from streamclip.clipper.ffmpeg_clipper import FfmpegClipper
from streamclip.config import Settings, get_settings
from streamclip.db import init_db, make_engine, make_session_factory
from streamclip.detection.audio_classifier import AudioEventClassifier
from streamclip.detection.chat_signals import ChatSignalDetector
from streamclip.detection.scorer import HighlightScorer
from streamclip.discord_bot.bot import build_bot
from streamclip.discord_bot.review_bot import DiscordReviewBot
from streamclip.models import Platform, Streamer, StreamSession
from streamclip.orchestrator.worker import (
    ChatEvent,
    ChunkEvent,
    Orchestrator,
    SessionRunner,
    TickEvent,
    merge_async_iterators,
)
from streamclip.platforms.base import PlatformAdapter
from streamclip.platforms.kick import KickAdapter, KickTokenProvider
from streamclip.platforms.twitch import TwitchAdapter, TwitchTokenProvider
from streamclip.platforms.youtube import YouTubeAdapter
from streamclip.publisher.post_for_me import PostForMeClient
from streamclip.recorder.streamlink_recorder import StreamlinkRecorder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("streamclip.worker")


def build_adapters(settings: Settings, http_client: httpx.AsyncClient) -> dict[Platform, PlatformAdapter]:
    adapters: dict[Platform, PlatformAdapter] = {}

    if settings.twitch_client_id and settings.twitch_client_secret:
        token_provider = TwitchTokenProvider(http_client, settings.twitch_client_id, settings.twitch_client_secret)
        adapters[Platform.TWITCH] = TwitchAdapter(http_client, settings.twitch_client_id, token_provider)
    else:
        logger.warning("Twitch credentials not configured - Twitch streamers will be skipped.")

    if settings.youtube_api_key:
        adapters[Platform.YOUTUBE] = YouTubeAdapter(http_client, settings.youtube_api_key)
    else:
        logger.warning("YouTube API key not configured - YouTube streamers will be skipped.")

    if settings.kick_client_id and settings.kick_client_secret:
        token_provider = KickTokenProvider(http_client, settings.kick_client_id, settings.kick_client_secret)
        adapters[Platform.KICK] = KickAdapter(http_client, token_provider)
    else:
        logger.warning("Kick credentials not configured - Kick streamers will be skipped.")

    return adapters


async def _ticks(interval_seconds: float):
    while True:
        await asyncio.sleep(interval_seconds)
        yield TickEvent(at=datetime.now(UTC))


class WorkerApp:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker,
        http_client: httpx.AsyncClient,
        discord_bot: DiscordReviewBot | None,
        publisher: PostForMeClient | None,
    ):
        self.settings = settings
        self.session_factory = session_factory
        self.http_client = http_client
        self.discord_bot = discord_bot
        self.publisher = publisher
        self.adapters = build_adapters(settings, http_client)
        self.orchestrator = Orchestrator(
            adapters=self.adapters, on_went_live=self._on_went_live, on_went_offline=self._on_went_offline
        )
        self._tasks: dict[int, asyncio.Task] = {}
        self._recorder_handles: dict[int, object] = {}

    async def _on_went_live(self, _db: AsyncSession, streamer: Streamer, stream_url: str | None) -> None:
        if streamer.id in self._tasks:
            return
        logger.info("Streamer %s (%s) went live", streamer.display_name, streamer.platform.value)
        if self.discord_bot:
            await self.discord_bot.notify_live(streamer.display_name, streamer.platform.value)
        self._tasks[streamer.id] = asyncio.create_task(self._run_session(streamer, stream_url or ""))

    async def _on_went_offline(self, _db: AsyncSession, streamer: Streamer) -> None:
        logger.info("Streamer %s went offline", streamer.display_name)
        task = self._tasks.pop(streamer.id, None)
        if task:
            task.cancel()

    async def _run_session(self, streamer: Streamer, stream_url: str) -> None:
        adapter = self.adapters[streamer.platform]
        recorder = StreamlinkRecorder(chunk_duration_seconds=self.settings.chunk_duration_seconds)

        async with self.session_factory() as db:
            db_streamer = await db.get(Streamer, streamer.id)
            session_row = StreamSession(streamer_id=db_streamer.id, stream_url=stream_url)
            db.add(session_row)
            await db.commit()
            await db.refresh(session_row)

        session_dir = Path(self.settings.recordings_dir) / f"session_{session_row.id}"
        handle = await recorder.start(stream_url, session_dir)
        self._recorder_handles[streamer.id] = handle

        async def chat_events():
            async for message in adapter.stream_chat(streamer.channel_id):
                yield ChatEvent(message)

        async def chunk_events():
            sequence = 0
            async for chunk in recorder.watch_chunks(handle, session_row.started_at):
                yield ChunkEvent(chunk=chunk, sequence=sequence)
                sequence += 1

        runner = SessionRunner(
            chat_detector=ChatSignalDetector(),
            audio_classifier=AudioEventClassifier(confidence_threshold=self.settings.audio_event_confidence_threshold),
            scorer=HighlightScorer(
                pre_roll_seconds=self.settings.highlight_pre_roll_seconds,
                post_roll_seconds=self.settings.highlight_post_roll_seconds,
            ),
            clipper=FfmpegClipper(),
            clips_dir=Path(self.settings.clips_dir),
        )

        try:
            async with self.session_factory() as db:
                events = merge_async_iterators(
                    chat_events(), chunk_events(), _ticks(interval_seconds=5.0)
                )
                created = await runner.run(db, session_row, events)
                for clip in created:
                    logger.info("Clip created for session %s at %.1fs", session_row.id, clip.trigger_offset_seconds)
                    if self.discord_bot:
                        await self.discord_bot.notify_clip_ready(clip, streamer.display_name)
        except asyncio.CancelledError:
            pass
        finally:
            await recorder_stop_safely(handle)
            self._recorder_handles.pop(streamer.id, None)
            async with self.session_factory() as db:
                row = await db.get(StreamSession, session_row.id)
                if row:
                    row.ended_at = datetime.now(UTC)
                    await db.commit()

    async def _on_clip_approved(self, clip) -> None:
        if not self.publisher:
            logger.info("Clip %s approved but no Post for Me API key configured - skipping publish.", clip.id)
            return
        caption = "Auto-clipped highlight"
        try:
            post = await self.publisher.publish_clip(Path(clip.file_path), caption)
            logger.info("Published clip %s as Post for Me post %s", clip.id, post.id)
        except Exception:
            logger.exception("Failed to publish clip %s", clip.id)

    async def poll_forever(self) -> None:
        while True:
            async with self.session_factory() as db:
                result = await db.execute(
                    select(Streamer).where(
                        Streamer.is_tracked.is_(True), Streamer.platform.in_(list(self.adapters.keys()))
                    )
                )
                streamers = list(result.scalars().all())
                await self.orchestrator.poll_once(db, streamers)
            await asyncio.sleep(self.settings.poll_interval_seconds)


async def recorder_stop_safely(handle) -> None:
    try:
        await handle.stop()
    except Exception:
        logger.exception("Error stopping recorder")


async def main() -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    await init_db(engine)
    session_factory = make_session_factory(engine)

    discord_bot_client = None
    review_bot = None
    publisher = None

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        if settings.post_for_me_api_key:
            publisher = PostForMeClient(http_client, settings.post_for_me_api_key)

        app = WorkerApp(settings, session_factory, http_client, discord_bot=None, publisher=publisher)
        app.discord_bot = None  # set below once the real bot exists, so callbacks can reference it

        tasks = [asyncio.create_task(app.poll_forever())]

        if settings.discord_bot_token and settings.discord_review_channel_id:
            discord_bot_client, review_bot = build_bot(
                session_factory, settings.discord_review_channel_id, on_approved=app._on_clip_approved
            )
            app.discord_bot = review_bot
            tasks.append(asyncio.create_task(discord_bot_client.start(settings.discord_bot_token)))
        else:
            logger.warning("Discord not configured - clips will sit pending with no review notifications.")

        logger.info("streamclip worker started. Tracking platforms: %s", list(app.adapters.keys()))
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
