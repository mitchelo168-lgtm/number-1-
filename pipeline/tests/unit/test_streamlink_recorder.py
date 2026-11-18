from datetime import datetime
from pathlib import Path

import pytest

from streamclip.recorder.streamlink_recorder import (
    RecordingHandle,
    StreamlinkRecorder,
    parse_segment_csv_line,
)


class FakeProcess:
    def __init__(self):
        self.returncode: int | None = None
        self.terminated = False

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    async def wait(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


@pytest.mark.parametrize(
    "line,expected",
    [
        ("chunk_000000.ts,0.000000,600.000000", ("chunk_000000.ts", 0.0, 600.0)),
        ("chunk_000001.ts, 600.0, 1200.0", ("chunk_000001.ts", 600.0, 1200.0)),
        ("", None),
        ("not,a,valid,line", None),
        ("missing,fields", None),
    ],
)
def test_parse_segment_csv_line(line, expected):
    assert parse_segment_csv_line(line) == expected


async def test_watch_chunks_yields_as_csv_grows_then_stops_when_process_exits():
    process = FakeProcess()
    handle = RecordingHandle(process=process, session_dir=Path("/fake"), segments_csv=Path("/fake/segments.csv"))

    # Simulate the csv file gaining one line per poll, then the process exiting.
    csv_states = [
        ["chunk_000000.ts,0.000000,600.000000"],
        ["chunk_000000.ts,0.000000,600.000000", "chunk_000001.ts,600.000000,1200.000000"],
    ]
    call_count = {"n": 0}

    async def fake_read_lines(path: Path) -> list[str]:
        idx = min(call_count["n"], len(csv_states) - 1)
        call_count["n"] += 1
        if call_count["n"] >= 2:
            process.returncode = 0  # process "exits" after the second poll
        return csv_states[idx]

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    recorder = StreamlinkRecorder(read_lines=fake_read_lines, sleep=fake_sleep, poll_interval_seconds=5.0)

    chunks = []
    async for chunk in recorder.watch_chunks(handle, session_started_at=datetime(2026, 11, 18, 12, 0, 0)):
        chunks.append(chunk)

    assert [c.file_path for c in chunks] == [
        str(Path("/fake") / "chunk_000000.ts"),
        str(Path("/fake") / "chunk_000001.ts"),
    ]
    assert chunks[0].duration_seconds == 600.0
    assert chunks[1].sequence == 1
    assert sleeps == [5.0]


async def test_recording_handle_stop_terminates_running_process():
    process = FakeProcess()
    handle = RecordingHandle(process=process, session_dir=Path("/fake"), segments_csv=Path("/fake/segments.csv"))

    await handle.stop()

    assert process.terminated is True
    assert handle.is_running is False


async def test_start_invokes_injected_pipeline_with_expected_paths(tmp_path):
    captured = {}

    async def fake_pipeline(stream_url, session_dir, segments_csv, chunk_duration):
        captured["stream_url"] = stream_url
        captured["session_dir"] = session_dir
        captured["segments_csv"] = segments_csv
        captured["chunk_duration"] = chunk_duration
        return FakeProcess()

    recorder = StreamlinkRecorder(chunk_duration_seconds=300.0, run_pipeline=fake_pipeline)
    handle = await recorder.start("https://twitch.tv/shroud", tmp_path)

    assert captured["stream_url"] == "https://twitch.tv/shroud"
    assert captured["session_dir"] == tmp_path
    assert captured["segments_csv"] == tmp_path / "segments.csv"
    assert captured["chunk_duration"] == 300.0
    assert handle.is_running is True
