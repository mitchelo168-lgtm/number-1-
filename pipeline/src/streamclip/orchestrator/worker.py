"""Wires platform adapters -> recorder -> detectors -> scorer -> clipper -> DB
into a running pipeline.

Two layers, each independently testable:

* `merge_async_iterators` / `SessionRunner` — drives ONE live session: fans
  chat messages, recorded chunks, and a periodic scoring tick into a single
  event stream, updates the chat/audio detectors, asks the `HighlightScorer`
  whether a clip should be cut, and persists any resulting `Clip`.
* `Orchestrator` — polls tracked streamers for live/offline transitions and
  starts/stops a `SessionRunner` for each one.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from streamclip.clipper.ffmpeg_clipper import FfmpegClipper, compute_chunk_offsets
from streamclip.detection.audio_classifier import (
    AudioEventClassifier,
    AudioEventScore,
    extract_audio_window,
)
from streamclip.detection.chat_signals import ChatSignalDetector
from streamclip.detection.scorer import HighlightScorer
from streamclip.models import (
    Clip,
    Platform,
    RecordingChunk,
    ReviewStatus,
    Streamer,
    StreamSession,
)
from streamclip.platforms.base import ChatMessage, PlatformAdapter
from streamclip.recorder.streamlink_recorder import ChunkInfo

# --- events a session's detection loop reacts to -----------------------------

@dataclass(frozen=True)
class ChatEvent:
    message: ChatMessage


@dataclass(frozen=True)
class ChunkEvent:
    chunk: ChunkInfo
    sequence: int


@dataclass(frozen=True)
class TickEvent:
    at: datetime


SessionEvent = ChatEvent | ChunkEvent | TickEvent


async def merge_async_iterators(*iterators: AsyncIterator) -> AsyncIterator:
    """Fan several async iterators into one, yielding items in arrival order
    and finishing once every source has been exhausted."""
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()
    remaining = len(iterators)

    async def _pump(it: AsyncIterator) -> None:
        try:
            async for item in it:
                await queue.put(item)
        finally:
            await queue.put(sentinel)

    tasks = [asyncio.create_task(_pump(it)) for it in iterators]
    try:
        while remaining > 0:
            item = await queue.get()
            if item is sentinel:
                remaining -= 1
                continue
            yield item
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class SessionRunner:
    """Runs the detection/clipping loop for a single live stream session."""

    def __init__(
        self,
        chat_detector: ChatSignalDetector,
        audio_classifier: AudioEventClassifier,
        scorer: HighlightScorer,
        clipper: FfmpegClipper,
        clips_dir: Path,
        audio_sample_seconds: float = 5.0,
        audio_recency_seconds: float = 20.0,
    ):
        self._chat_detector = chat_detector
        self._audio_classifier = audio_classifier
        self._scorer = scorer
        self._clipper = clipper
        self._clips_dir = clips_dir
        self._audio_sample_seconds = audio_sample_seconds
        self._audio_recency_seconds = audio_recency_seconds

        self._raw_chunks: list[tuple[int, str, float]] = []
        self._latest_audio_score: AudioEventScore | None = None
        self._latest_audio_offset: float | None = None

    async def run(
        self, db: AsyncSession, session_row: StreamSession, events: AsyncIterator[SessionEvent]
    ) -> list[Clip]:
        created: list[Clip] = []
        async for event in events:
            if isinstance(event, ChatEvent):
                self._chat_detector.add_message(event.message)
            elif isinstance(event, ChunkEvent):
                await self._handle_chunk(db, session_row, event)
            elif isinstance(event, TickEvent):
                clip = await self._handle_tick(db, session_row, event)
                if clip is not None:
                    created.append(clip)
        return created

    async def _handle_chunk(self, db: AsyncSession, session_row: StreamSession, event: ChunkEvent) -> None:
        chunk = event.chunk
        db.add(
            RecordingChunk(
                session_id=session_row.id,
                sequence=event.sequence,
                file_path=chunk.file_path,
                started_at=chunk.started_at,
                duration_seconds=chunk.duration_seconds,
            )
        )
        self._raw_chunks.append((event.sequence, chunk.file_path, chunk.duration_seconds))
        await db.flush()
        await self._sample_audio(chunk, event.sequence)

    async def _sample_audio(self, chunk: ChunkInfo, sequence: int) -> None:
        offset_in_chunk = max(0.0, chunk.duration_seconds - self._audio_sample_seconds)
        window = min(self._audio_sample_seconds, chunk.duration_seconds)
        try:
            samples, sample_rate = await extract_audio_window(Path(chunk.file_path), offset_in_chunk, window)
        except Exception:  # noqa: BLE001 - audio scoring is best-effort; any failure here (missing
            return  # ffmpeg, bad file, model not installed) should degrade to chat-only, not crash the session.

        chunk_refs = compute_chunk_offsets(self._raw_chunks)
        this_ref = next((r for r in chunk_refs if r.sequence == sequence), None)
        if this_ref is None:
            return
        absolute_offset = this_ref.start_offset_seconds + offset_in_chunk
        self._latest_audio_score = self._audio_classifier.score_window(samples, sample_rate, absolute_offset)
        self._latest_audio_offset = absolute_offset

    async def _handle_tick(
        self, db: AsyncSession, session_row: StreamSession, event: TickEvent
    ) -> Clip | None:
        offset_seconds = (event.at - session_row.started_at).total_seconds()

        chat_score = self._chat_detector.score_at(event.at)
        audio_score = None
        if (
            self._latest_audio_score is not None
            and self._latest_audio_offset is not None
            and offset_seconds - self._latest_audio_offset <= self._audio_recency_seconds
        ):
            audio_score = self._latest_audio_score

        combined = self._scorer.combine(offset_seconds, chat_score, audio_score)
        window = self._scorer.process(combined)
        if window is None:
            return None

        chunk_refs = compute_chunk_offsets(self._raw_chunks)
        try:
            output_path = self._clips_dir / f"session_{session_row.id}_t{int(window.trigger_offset_seconds)}.ts"
            await self._clipper.extract_clip(chunk_refs, window.start_seconds, window.end_seconds, output_path)
        except ValueError:
            # The clip's trailing chunk hasn't been flushed to disk yet (a
            # normal race right after a trigger); skip rather than crash the
            # whole session loop. It will simply be missed this tick.
            return None

        clip = Clip(
            session_id=session_row.id,
            file_path=str(output_path),
            trigger_offset_seconds=window.trigger_offset_seconds,
            clip_start_seconds=window.start_seconds,
            clip_end_seconds=window.end_seconds,
            highlight_score=window.highlight_score,
            signal_breakdown=window.signal_breakdown,
            review_status=ReviewStatus.PENDING,
        )
        db.add(clip)
        await db.flush()
        return clip


# --- top-level poll / transition / session lifecycle -------------------------

@dataclass(frozen=True)
class LiveTransition:
    streamer_id: int
    channel_id: str
    went_live: bool
    stream_url: str | None = None


def compute_transitions(
    previous_live: dict[int, bool],
    current_status: dict[int, tuple[str, bool, str | None]],
) -> list[LiveTransition]:
    """`current_status` maps streamer_id -> (channel_id, is_live, stream_url)."""
    transitions = []
    for streamer_id, (channel_id, is_live, stream_url) in current_status.items():
        was_live = previous_live.get(streamer_id, False)
        if is_live and not was_live:
            transitions.append(LiveTransition(streamer_id, channel_id, went_live=True, stream_url=stream_url))
        elif not is_live and was_live:
            transitions.append(LiveTransition(streamer_id, channel_id, went_live=False))
    return transitions


class Orchestrator:
    def __init__(
        self,
        adapters: dict[Platform, PlatformAdapter],
        on_went_live: Callable[[AsyncSession, Streamer, str | None], None] | None = None,
        on_went_offline: Callable[[AsyncSession, Streamer], None] | None = None,
    ):
        self._adapters = adapters
        self._previous_live: dict[int, bool] = {}
        self._on_went_live = on_went_live
        self._on_went_offline = on_went_offline

    async def poll_once(self, db: AsyncSession, streamers: list[Streamer]) -> list[LiveTransition]:
        current_status: dict[int, tuple[str, bool, str | None]] = {}
        streamers_by_id = {s.id: s for s in streamers}

        for streamer in streamers:
            adapter = self._adapters[streamer.platform]
            status = await adapter.check_live(streamer.channel_id)
            current_status[streamer.id] = (streamer.channel_id, status.is_live, status.stream_url)

        transitions = compute_transitions(self._previous_live, current_status)
        self._previous_live = {sid: is_live for sid, (_, is_live, _) in current_status.items()}

        for transition in transitions:
            streamer = streamers_by_id[transition.streamer_id]
            if transition.went_live and self._on_went_live:
                await self._maybe_await(self._on_went_live(db, streamer, transition.stream_url))
            elif not transition.went_live and self._on_went_offline:
                await self._maybe_await(self._on_went_offline(db, streamer))

        return transitions

    @staticmethod
    async def _maybe_await(result):
        if asyncio.iscoroutine(result):
            return await result
        return result
