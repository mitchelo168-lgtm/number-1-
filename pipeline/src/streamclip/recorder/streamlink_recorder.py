"""Chunked stream recording via streamlink piped into ffmpeg's segment muxer.

The pipeline run for each session is, conceptually:

    streamlink <url> best --stdout | \\
        ffmpeg -i pipe:0 -c copy -f segment -segment_time <chunk_seconds> \\
               -reset_timestamps 1 -segment_list <segments.csv> -segment_list_type csv \\
               chunk_%06d.ts

`-segment_list ... -segment_list_type csv` is what makes chunk completion
observable: ffmpeg appends one `path,start,end` line to that CSV the moment
a segment file is finalized (not when it starts), so polling the CSV is a
reliable way to know a chunk is done and ready to hand to the detector /
clipper — we never read a line until ffmpeg has flushed it.
"""

import asyncio
import shlex
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class ChunkInfo:
    sequence: int
    file_path: str
    duration_seconds: float
    started_at: datetime


def parse_segment_csv_line(line: str) -> tuple[str, float, float] | None:
    """Parse one `path,start,end` line from ffmpeg's segment_list csv output."""
    parts = [p.strip() for p in line.strip().split(",")]
    if len(parts) != 3:
        return None
    path, start, end = parts
    try:
        return path, float(start), float(end)
    except ValueError:
        return None


class RecordingHandle:
    def __init__(self, process: asyncio.subprocess.Process, session_dir: Path, segments_csv: Path):
        self.process = process
        self.session_dir = session_dir
        self.segments_csv = segments_csv

    async def stop(self) -> None:
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=10)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()

    @property
    def is_running(self) -> bool:
        return self.process.returncode is None


PipelineRunner = Callable[[str, Path, Path, float], Awaitable[asyncio.subprocess.Process]]
ReadLines = Callable[[Path], Awaitable[list[str]]]


async def _default_read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text().splitlines()


class StreamlinkRecorder:
    def __init__(
        self,
        chunk_duration_seconds: float = 600.0,
        run_pipeline: PipelineRunner | None = None,
        read_lines: ReadLines | None = None,
        poll_interval_seconds: float = 2.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._chunk_duration = chunk_duration_seconds
        self._run_pipeline = run_pipeline or self._default_run_pipeline
        self._read_lines = read_lines or _default_read_lines
        self._poll_interval = poll_interval_seconds
        self._sleep = sleep

    async def _default_run_pipeline(
        self, stream_url: str, session_dir: Path, segments_csv: Path, chunk_duration: float
    ) -> asyncio.subprocess.Process:
        session_dir.mkdir(parents=True, exist_ok=True)
        pattern = str(session_dir / "chunk_%06d.ts")
        cmd = (
            f"streamlink {shlex.quote(stream_url)} best --stdout --loglevel warning | "
            f"ffmpeg -loglevel warning -i pipe:0 -c copy -f segment "
            f"-segment_time {chunk_duration} -reset_timestamps 1 "
            f"-segment_list {shlex.quote(str(segments_csv))} -segment_list_type csv "
            f"{shlex.quote(pattern)}"
        )
        return await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )

    async def start(self, stream_url: str, session_dir: Path) -> RecordingHandle:
        segments_csv = session_dir / "segments.csv"
        process = await self._run_pipeline(stream_url, session_dir, segments_csv, self._chunk_duration)
        return RecordingHandle(process=process, session_dir=session_dir, segments_csv=segments_csv)

    async def watch_chunks(self, handle: RecordingHandle, session_started_at: datetime) -> AsyncIterator[ChunkInfo]:
        """Yield each chunk as ffmpeg finalizes it, until the process exits."""
        seen = 0
        cumulative_seconds = 0.0
        while True:
            lines = await self._read_lines(handle.segments_csv)
            new_lines = lines[seen:]
            for line in new_lines:
                parsed = parse_segment_csv_line(line)
                if not parsed:
                    continue
                path, start, end = parsed
                duration = end - start
                # ffmpeg's segment_list only ever records the basename, even
                # when the output pattern it was given was an absolute path.
                absolute_path = str(handle.session_dir / path)
                yield ChunkInfo(
                    sequence=seen,
                    file_path=absolute_path,
                    duration_seconds=duration,
                    started_at=session_started_at + timedelta(seconds=cumulative_seconds),
                )
                cumulative_seconds += duration
                seen += 1

            if not handle.is_running and len(lines) == seen:
                return
            await self._sleep(self._poll_interval)
