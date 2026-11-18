"""Turns a highlight's [start_seconds, end_seconds) window (relative to
stream start) into an actual clip file, trimming/concatenating whichever
recorded chunks the window overlaps.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChunkRef:
    sequence: int
    file_path: str
    start_offset_seconds: float
    duration_seconds: float

    @property
    def end_offset_seconds(self) -> float:
        return self.start_offset_seconds + self.duration_seconds


def compute_chunk_offsets(chunks: list[tuple[int, str, float]]) -> list[ChunkRef]:
    """Turn (sequence, file_path, duration_seconds) tuples into ChunkRefs with
    cumulative start offsets, ordered by sequence."""
    ordered = sorted(chunks, key=lambda c: c[0])
    refs = []
    cursor = 0.0
    for sequence, file_path, duration in ordered:
        refs.append(ChunkRef(sequence=sequence, file_path=file_path, start_offset_seconds=cursor, duration_seconds=duration))
        cursor += duration
    return refs


def select_overlapping_chunks(
    chunks: list[ChunkRef], start_seconds: float, end_seconds: float
) -> list[tuple[ChunkRef, float, float]]:
    """Return (chunk, local_start, local_end) for every chunk that overlaps
    [start_seconds, end_seconds), with local_* expressed as offsets within
    that chunk's own file."""
    result = []
    for chunk in chunks:
        overlap_start = max(start_seconds, chunk.start_offset_seconds)
        overlap_end = min(end_seconds, chunk.end_offset_seconds)
        if overlap_start < overlap_end:
            result.append((chunk, overlap_start - chunk.start_offset_seconds, overlap_end - chunk.start_offset_seconds))
    return result


RunFfmpeg = Callable[[list[str]], Awaitable[None]]


async def _default_run_ffmpeg(args: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg exited with code {proc.returncode}: {' '.join(args)}")


class FfmpegClipper:
    def __init__(self, run_ffmpeg: RunFfmpeg = _default_run_ffmpeg):
        self._run_ffmpeg = run_ffmpeg

    async def extract_clip(
        self, chunks: list[ChunkRef], start_seconds: float, end_seconds: float, output_path: Path
    ) -> Path:
        overlaps = select_overlapping_chunks(chunks, start_seconds, end_seconds)
        if not overlaps:
            raise ValueError(
                f"no recorded chunk overlaps the requested window [{start_seconds}, {end_seconds})"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if len(overlaps) == 1:
            chunk, local_start, local_end = overlaps[0]
            await self._run_ffmpeg(_trim_args(chunk.file_path, local_start, local_end - local_start, output_path))
            return output_path

        parts_dir = output_path.parent / f".{output_path.stem}_parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        part_paths: list[Path] = []
        for i, (chunk, local_start, local_end) in enumerate(overlaps):
            part_path = parts_dir / f"part_{i:03d}.ts"
            await self._run_ffmpeg(_trim_args(chunk.file_path, local_start, local_end - local_start, part_path))
            part_paths.append(part_path)

        concat_list = parts_dir / "concat.txt"
        concat_list.write_text("\n".join(f"file '{p}'" for p in part_paths) + "\n")
        await self._run_ffmpeg(
            ["-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(output_path)]
        )
        return output_path


def _trim_args(input_path: str, local_start: float, duration: float, output_path: Path) -> list[str]:
    return ["-y", "-ss", str(local_start), "-i", input_path, "-t", str(duration), "-c", "copy", str(output_path)]
