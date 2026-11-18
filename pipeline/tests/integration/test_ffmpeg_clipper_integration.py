import asyncio
import json
from pathlib import Path

import pytest

from streamclip.clipper.ffmpeg_clipper import ChunkRef, FfmpegClipper

pytestmark = pytest.mark.integration


async def _make_chunk(path: Path, duration: float, color: str) -> None:
    cmd = (
        f"ffmpeg -loglevel error -f lavfi -i color=c={color}:size=160x120:rate=10:duration={duration} "
        f"-c:v libx264 -g 10 {path}"
    )
    proc = await asyncio.create_subprocess_shell(cmd)
    await proc.wait()


async def _probe_duration(path: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)
    stdout, _ = await proc.communicate()
    return float(json.loads(stdout)["format"]["duration"])


async def test_extract_clip_spanning_two_real_chunks(tmp_path: Path):
    chunk_a = tmp_path / "chunk_000000.ts"
    chunk_b = tmp_path / "chunk_000001.ts"
    await _make_chunk(chunk_a, duration=5.0, color="red")
    await _make_chunk(chunk_b, duration=5.0, color="blue")

    refs = [
        ChunkRef(sequence=0, file_path=str(chunk_a), start_offset_seconds=0.0, duration_seconds=5.0),
        ChunkRef(sequence=1, file_path=str(chunk_b), start_offset_seconds=5.0, duration_seconds=5.0),
    ]

    clipper = FfmpegClipper()
    output = tmp_path / "clip.ts"

    result = await clipper.extract_clip(refs, start_seconds=3.0, end_seconds=7.0, output_path=output)

    assert result.exists()
    assert result.stat().st_size > 0
    duration = await _probe_duration(result)
    assert duration == pytest.approx(4.0, abs=0.5)
