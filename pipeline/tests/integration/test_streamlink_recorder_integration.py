import asyncio
import shlex
from datetime import datetime
from pathlib import Path

import pytest

from streamclip.recorder.streamlink_recorder import StreamlinkRecorder

pytestmark = pytest.mark.integration


async def _run_synthetic_ffmpeg_pipeline(stream_url, session_dir: Path, segments_csv: Path, chunk_duration: float):
    """Stand-in for the real streamlink|ffmpeg pipeline: generates a short
    synthetic test video with ffmpeg's own lavfi source instead of pulling
    from a real stream, so this test exercises the *real* ffmpeg segment +
    segment_list mechanism without needing network access or a live stream.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(session_dir / "chunk_%06d.ts")
    # -g/-keyint_min align keyframes to the segment boundary: ffmpeg's segment
    # muxer can only cut on a keyframe, so without a matching GOP size it
    # would just merge everything into one segment regardless of -segment_time.
    fps = 10
    gop = int(fps * chunk_duration)
    cmd = (
        f"ffmpeg -loglevel error -f lavfi -i testsrc=size=160x120:rate={fps} -t 5 "
        f"-c:v libx264 -g {gop} -keyint_min {gop} -sc_threshold 0 "
        f"-f segment -segment_time {chunk_duration} -reset_timestamps 1 "
        f"-segment_list {shlex.quote(str(segments_csv))} -segment_list_type csv "
        f"{shlex.quote(pattern)}"
    )
    return await asyncio.create_subprocess_shell(cmd)


async def test_watch_chunks_against_real_ffmpeg_segment_output(tmp_path):
    recorder = StreamlinkRecorder(
        chunk_duration_seconds=2.0,
        run_pipeline=_run_synthetic_ffmpeg_pipeline,
        poll_interval_seconds=0.2,
    )

    session_dir = tmp_path / "session"
    handle = await recorder.start("ignored://synthetic", session_dir)

    chunks = []
    async for chunk in recorder.watch_chunks(handle, session_started_at=datetime(2026, 11, 18, 12, 0, 0)):
        chunks.append(chunk)

    # ~5s of video cut into 2s segments -> 3 chunks (2s, 2s, ~1s tail)
    assert len(chunks) == 3
    for chunk in chunks:
        assert Path(chunk.file_path).exists()
        assert Path(chunk.file_path).stat().st_size > 0
    assert chunks[0].duration_seconds == pytest.approx(2.0, abs=0.5)
    assert chunks[-1].duration_seconds < 2.0
