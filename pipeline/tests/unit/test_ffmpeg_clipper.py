from pathlib import Path

import pytest

from streamclip.clipper.ffmpeg_clipper import (
    ChunkRef,
    FfmpegClipper,
    compute_chunk_offsets,
    select_overlapping_chunks,
)


def test_compute_chunk_offsets_accumulates_durations_in_sequence_order():
    chunks = [(1, "b.ts", 600.0), (0, "a.ts", 600.0), (2, "c.ts", 300.0)]
    refs = compute_chunk_offsets(chunks)

    assert [r.file_path for r in refs] == ["a.ts", "b.ts", "c.ts"]
    assert [r.start_offset_seconds for r in refs] == [0.0, 600.0, 1200.0]
    assert refs[2].end_offset_seconds == 1500.0


def test_select_overlapping_chunks_window_within_single_chunk():
    refs = compute_chunk_offsets([(0, "a.ts", 600.0), (1, "b.ts", 600.0)])

    overlaps = select_overlapping_chunks(refs, start_seconds=100.0, end_seconds=150.0)

    assert len(overlaps) == 1
    chunk, local_start, local_end = overlaps[0]
    assert chunk.file_path == "a.ts"
    assert (local_start, local_end) == (100.0, 150.0)


def test_select_overlapping_chunks_window_spans_chunk_boundary():
    refs = compute_chunk_offsets([(0, "a.ts", 600.0), (1, "b.ts", 600.0)])

    overlaps = select_overlapping_chunks(refs, start_seconds=580.0, end_seconds=620.0)

    assert [c.file_path for c, _, _ in overlaps] == ["a.ts", "b.ts"]
    (a_chunk, a_start, a_end), (b_chunk, b_start, b_end) = overlaps
    assert (a_start, a_end) == (580.0, 600.0)
    assert (b_start, b_end) == (0.0, 20.0)


def test_select_overlapping_chunks_window_spans_three_chunks():
    refs = compute_chunk_offsets([(0, "a.ts", 10.0), (1, "b.ts", 10.0), (2, "c.ts", 10.0)])

    overlaps = select_overlapping_chunks(refs, start_seconds=5.0, end_seconds=25.0)

    assert [c.file_path for c, _, _ in overlaps] == ["a.ts", "b.ts", "c.ts"]
    assert overlaps[1] == (refs[1], 0.0, 10.0)  # middle chunk fully included


def test_select_overlapping_chunks_no_overlap_returns_empty():
    refs = compute_chunk_offsets([(0, "a.ts", 10.0)])

    assert select_overlapping_chunks(refs, start_seconds=20.0, end_seconds=30.0) == []


async def test_extract_clip_single_chunk_calls_ffmpeg_with_trim_args():
    calls = []

    async def fake_run(args):
        calls.append(args)

    clipper = FfmpegClipper(run_ffmpeg=fake_run)
    refs = [ChunkRef(sequence=0, file_path="a.ts", start_offset_seconds=0.0, duration_seconds=600.0)]
    output = Path("/out/clip.mp4")

    result = await clipper.extract_clip(refs, start_seconds=100.0, end_seconds=140.0, output_path=output)

    assert result == output
    assert len(calls) == 1
    args = calls[0]
    assert "-ss" in args and args[args.index("-ss") + 1] == "100.0"
    assert "-t" in args and args[args.index("-t") + 1] == "40.0"
    assert args[-1] == str(output)


async def test_extract_clip_multi_chunk_trims_each_part_then_concats(tmp_path):
    calls = []

    async def fake_run(args):
        calls.append(args)
        # Simulate ffmpeg actually producing the concat list's referenced files
        # so no assertions about file existence are needed here; the real
        # concat-file writing is exercised for real in the integration test.

    clipper = FfmpegClipper(run_ffmpeg=fake_run)
    refs = [
        ChunkRef(sequence=0, file_path="a.ts", start_offset_seconds=0.0, duration_seconds=10.0),
        ChunkRef(sequence=1, file_path="b.ts", start_offset_seconds=10.0, duration_seconds=10.0),
    ]
    output = tmp_path / "clip.mp4"

    await clipper.extract_clip(refs, start_seconds=5.0, end_seconds=15.0, output_path=output)

    # two trims (one per overlapping chunk) + one concat call
    assert len(calls) == 3
    trim_a, trim_b, concat_call = calls
    assert trim_a[trim_a.index("-i") + 1] == "a.ts"
    assert trim_b[trim_b.index("-i") + 1] == "b.ts"
    assert "-f" in concat_call and concat_call[concat_call.index("-f") + 1] == "concat"
    assert concat_call[-1] == str(output)

    concat_list = tmp_path / ".clip_parts" / "concat.txt"
    assert concat_list.exists()
    assert "part_000.ts" in concat_list.read_text()
    assert "part_001.ts" in concat_list.read_text()


async def test_extract_clip_raises_when_no_chunk_overlaps():
    clipper = FfmpegClipper(run_ffmpeg=lambda args: None)
    refs = [ChunkRef(sequence=0, file_path="a.ts", start_offset_seconds=0.0, duration_seconds=10.0)]

    with pytest.raises(ValueError, match="no recorded chunk overlaps"):
        await clipper.extract_clip(refs, start_seconds=100.0, end_seconds=110.0, output_path=Path("/out/x.mp4"))
