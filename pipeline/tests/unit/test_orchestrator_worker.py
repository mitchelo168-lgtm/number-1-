import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from streamclip.clipper.ffmpeg_clipper import FfmpegClipper
from streamclip.detection.audio_classifier import AudioEventClassifier
from streamclip.detection.chat_signals import ChatSignalDetector
from streamclip.detection.scorer import HighlightScorer
from streamclip.models import Clip, Platform, RecordingChunk, StreamSession, Streamer
from streamclip.orchestrator.worker import (
    ChatEvent,
    ChunkEvent,
    LiveTransition,
    Orchestrator,
    SessionRunner,
    TickEvent,
    compute_transitions,
    merge_async_iterators,
)
from streamclip.platforms.base import ChatMessage, LiveStatus
from streamclip.recorder.streamlink_recorder import ChunkInfo

T0 = datetime(2026, 11, 18, 12, 0, 0)


# --- merge_async_iterators ---------------------------------------------------

async def _slow_source(items, delay):
    for item in items:
        await asyncio.sleep(delay)
        yield item


async def test_merge_async_iterators_yields_all_items_from_every_source():
    fast = _slow_source(["a1", "a2", "a3"], delay=0.001)
    slow = _slow_source(["b1", "b2"], delay=0.003)

    collected = []
    async for item in merge_async_iterators(fast, slow):
        collected.append(item)

    assert sorted(collected) == sorted(["a1", "a2", "a3", "b1", "b2"])


async def test_merge_async_iterators_handles_empty_sources():
    async def empty():
        return
        yield  # pragma: no cover - makes this an async generator

    collected = [item async for item in merge_async_iterators(empty(), empty())]
    assert collected == []


# --- compute_transitions -----------------------------------------------------

def test_compute_transitions_detects_went_live_and_went_offline():
    previous = {1: False, 2: True}
    current = {1: ("a", True, "url-a"), 2: ("b", False, None)}

    transitions = compute_transitions(previous, current)

    assert LiveTransition(1, "a", went_live=True, stream_url="url-a") in transitions
    assert LiveTransition(2, "b", went_live=False) in transitions
    assert len(transitions) == 2


def test_compute_transitions_no_change_yields_nothing():
    previous = {1: True}
    current = {1: ("a", True, "url-a")}

    assert compute_transitions(previous, current) == []


def test_compute_transitions_first_time_seen_live_counts_as_went_live():
    transitions = compute_transitions({}, {1: ("a", True, "url-a")})
    assert transitions == [LiveTransition(1, "a", went_live=True, stream_url="url-a")]


# --- SessionRunner ------------------------------------------------------------

async def _ordered_events(*events):
    for event in events:
        yield event


async def test_session_runner_creates_a_clip_on_chat_spike(db_session):
    streamer = Streamer(platform=Platform.TWITCH, channel_id="shroud", display_name="shroud")
    db_session.add(streamer)
    await db_session.flush()
    session_row = StreamSession(streamer_id=streamer.id, stream_url="https://twitch.tv/shroud", started_at=T0)
    db_session.add(session_row)
    await db_session.flush()

    recorded_ffmpeg_calls = []

    async def fake_run_ffmpeg(args):
        recorded_ffmpeg_calls.append(args)

    runner = SessionRunner(
        chat_detector=ChatSignalDetector(window_seconds=10.0, baseline_window_seconds=60.0, zscore_threshold=2.0),
        audio_classifier=AudioEventClassifier(classify=lambda s, r: []),
        scorer=HighlightScorer(pre_roll_seconds=40.0, post_roll_seconds=10.0),
        clipper=FfmpegClipper(run_ffmpeg=fake_run_ffmpeg),
        clips_dir=Path("/tmp/streamclip-test-clips"),
    )

    chunk_event = ChunkEvent(
        chunk=ChunkInfo(sequence=0, file_path="/nonexistent/chunk_000000.ts", duration_seconds=600.0, started_at=T0),
        sequence=0,
    )

    chat_events = [
        ChatEvent(ChatMessage(author="u", text="chat is calm", timestamp=T0 + timedelta(seconds=i * 10)))
        for i in range(5)
    ] + [
        ChatEvent(ChatMessage(author=f"u{i}", text="that was crazy!!", timestamp=T0 + timedelta(seconds=55 + i * 0.2)))
        for i in range(20)
    ]
    tick_event = TickEvent(at=T0 + timedelta(seconds=59))

    created = await runner.run(db_session, session_row, _ordered_events(chunk_event, *chat_events, tick_event))
    await db_session.commit()

    assert len(created) == 1
    clip = created[0]
    assert clip.session_id == session_row.id
    assert clip.clip_start_seconds == pytest.approx(19.0)
    assert clip.clip_end_seconds == pytest.approx(69.0)
    # classify stub reports no detected events -> a real-but-empty audio
    # score of 0.0, not "no signal"; the clip still fires purely off chat.
    assert clip.signal_breakdown["audio"] == pytest.approx(0.0)

    result = await db_session.execute(select(Clip).where(Clip.session_id == session_row.id))
    assert len(result.scalars().all()) == 1

    chunks = await db_session.execute(select(RecordingChunk).where(RecordingChunk.session_id == session_row.id))
    assert len(chunks.scalars().all()) == 1
    assert len(recorded_ffmpeg_calls) == 1  # the clip-extraction trim call


async def test_session_runner_produces_no_clip_when_chat_stays_quiet(db_session):
    streamer = Streamer(platform=Platform.TWITCH, channel_id="calmstreamer", display_name="calmstreamer")
    db_session.add(streamer)
    await db_session.flush()
    session_row = StreamSession(streamer_id=streamer.id, stream_url="https://twitch.tv/calmstreamer", started_at=T0)
    db_session.add(session_row)
    await db_session.flush()

    runner = SessionRunner(
        chat_detector=ChatSignalDetector(window_seconds=10.0, baseline_window_seconds=60.0),
        audio_classifier=AudioEventClassifier(classify=lambda s, r: []),
        scorer=HighlightScorer(),
        clipper=FfmpegClipper(run_ffmpeg=lambda args: asyncio.sleep(0)),
        clips_dir=Path("/tmp/streamclip-test-clips"),
    )

    chat_events = [
        ChatEvent(ChatMessage(author="u", text="hey", timestamp=T0 + timedelta(seconds=i * 10))) for i in range(6)
    ]
    tick_event = TickEvent(at=T0 + timedelta(seconds=55))

    created = await runner.run(db_session, session_row, _ordered_events(*chat_events, tick_event))

    assert created == []


# --- Orchestrator -------------------------------------------------------------

class FakeAdapter:
    def __init__(self, statuses: list[LiveStatus]):
        self._statuses = iter(statuses)

    async def check_live(self, channel_id):
        return next(self._statuses)

    def stream_chat(self, channel_id):
        raise NotImplementedError


async def test_orchestrator_fires_went_live_then_went_offline_callbacks():
    adapter = FakeAdapter(
        [
            LiveStatus(is_live=True, stream_url="https://twitch.tv/x"),
            LiveStatus(is_live=False),
        ]
    )
    went_live_calls = []
    went_offline_calls = []

    orchestrator = Orchestrator(
        adapters={Platform.TWITCH: adapter},
        on_went_live=lambda db, streamer, url: went_live_calls.append((streamer.id, url)),
        on_went_offline=lambda db, streamer: went_offline_calls.append(streamer.id),
    )

    streamer = Streamer(id=1, platform=Platform.TWITCH, channel_id="x", display_name="x")

    await orchestrator.poll_once(db=None, streamers=[streamer])
    await orchestrator.poll_once(db=None, streamers=[streamer])

    assert went_live_calls == [(1, "https://twitch.tv/x")]
    assert went_offline_calls == [1]


async def test_orchestrator_no_callback_when_status_unchanged():
    adapter = FakeAdapter([LiveStatus(is_live=False), LiveStatus(is_live=False)])
    went_live_calls = []

    orchestrator = Orchestrator(
        adapters={Platform.TWITCH: adapter},
        on_went_live=lambda db, streamer, url: went_live_calls.append(streamer.id),
    )
    streamer = Streamer(id=2, platform=Platform.TWITCH, channel_id="y", display_name="y")

    await orchestrator.poll_once(db=None, streamers=[streamer])
    await orchestrator.poll_once(db=None, streamers=[streamer])

    assert went_live_calls == []
