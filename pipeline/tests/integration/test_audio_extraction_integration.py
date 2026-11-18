import asyncio
from pathlib import Path

import pytest

from streamclip.detection.audio_classifier import extract_audio_window

pytestmark = pytest.mark.integration


async def test_extract_audio_window_against_real_ffmpeg_sine_wave(tmp_path: Path):
    # Build a 3-second, 440Hz sine wave test file with ffmpeg's own source generator.
    source = tmp_path / "tone.wav"
    cmd = (
        f"ffmpeg -loglevel error -f lavfi -i 'sine=frequency=440:duration=3' "
        f"-ar 44100 {source}"
    )
    proc = await asyncio.create_subprocess_shell(cmd)
    await proc.wait()
    assert source.exists()

    samples, sample_rate = await extract_audio_window(
        source, offset_seconds=1.0, duration_seconds=1.0, sample_rate=16000
    )

    assert sample_rate == 16000
    # 1 second @ 16kHz mono -> ~16000 samples (allow ffmpeg rounding slack)
    assert abs(len(samples) - 16000) < 50
    assert all(-1.0 <= s <= 1.0 for s in samples)
    # A real sine tone isn't silence.
    assert max(abs(s) for s in samples) > 0.1
