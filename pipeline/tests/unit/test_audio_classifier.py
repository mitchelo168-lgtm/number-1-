import struct
from pathlib import Path

import pytest

from streamclip.detection.audio_classifier import AudioEventClassifier, extract_audio_window


def fake_classify_factory(results: list[dict]):
    def _classify(samples, sample_rate):
        return results
    return _classify


def test_laughter_label_triggers_highlight():
    classifier = AudioEventClassifier(
        classify=fake_classify_factory([{"label": "Laughter", "score": 0.9}, {"label": "Speech", "score": 0.3}]),
        confidence_threshold=0.6,
    )
    score = classifier.score_window([0.0] * 16000, 16000, offset_seconds=30.0)

    assert score.top_label == "Laughter"
    assert score.event_confidence == pytest.approx(0.9)
    assert score.is_highlight is True


def test_unrelated_labels_do_not_trigger_highlight():
    classifier = AudioEventClassifier(
        classify=fake_classify_factory([{"label": "Speech", "score": 0.95}, {"label": "Music", "score": 0.4}]),
        confidence_threshold=0.6,
    )
    score = classifier.score_window([0.0] * 16000, 16000, offset_seconds=10.0)

    assert score.top_label == "Speech"  # highest raw score, for diagnostics
    assert score.event_confidence == 0.0  # neither label is in the target weight table
    assert score.is_highlight is False


def test_weighted_combination_prefers_strongest_weighted_signal():
    classifier = AudioEventClassifier(
        classify=fake_classify_factory(
            [
                {"label": "Crowd", "score": 0.9},  # weight 0.6 -> 0.54
                {"label": "Cheering", "score": 0.7},  # weight 1.0 -> 0.70
            ]
        ),
        confidence_threshold=0.6,
    )
    score = classifier.score_window([0.0] * 16000, 16000, offset_seconds=0.0)

    assert score.event_confidence == pytest.approx(0.7)
    assert score.is_highlight is True


def test_score_below_threshold_is_not_a_highlight():
    classifier = AudioEventClassifier(
        classify=fake_classify_factory([{"label": "Laughter", "score": 0.5}]),
        confidence_threshold=0.6,
    )
    score = classifier.score_window([0.0] * 16000, 16000, offset_seconds=0.0)

    assert score.event_confidence == pytest.approx(0.5)
    assert score.is_highlight is False


def test_missing_audio_extras_raises_actionable_error():
    classifier = AudioEventClassifier()  # no injected classify -> tries to import transformers
    with pytest.raises(RuntimeError, match="pip install -e '.\\[audio\\]'"):
        classifier.score_window([0.0] * 16000, 16000, offset_seconds=0.0)


async def test_extract_audio_window_decodes_pcm_bytes_to_normalized_floats():
    # Two int16 samples: 16384 (-> 0.5) and -16384 (-> -0.5)
    raw_bytes = struct.pack("<2h", 16384, -16384)

    async def fake_run_ffmpeg(chunk_path, offset_seconds, duration_seconds, sample_rate):
        assert chunk_path == Path("/fake/chunk.ts")
        assert offset_seconds == 12.5
        assert duration_seconds == 2.0
        assert sample_rate == 16000
        return raw_bytes

    samples, sample_rate = await extract_audio_window(
        Path("/fake/chunk.ts"), offset_seconds=12.5, duration_seconds=2.0, run_ffmpeg=fake_run_ffmpeg
    )

    assert sample_rate == 16000
    assert samples == pytest.approx([0.5, -0.5], abs=1e-4)


async def test_extract_audio_window_handles_odd_trailing_byte():
    async def fake_run_ffmpeg(*args, **kwargs):
        return struct.pack("<1h", 1000) + b"\x01"  # one valid sample + a stray trailing byte

    samples, _ = await extract_audio_window(Path("/fake/chunk.ts"), 0.0, 1.0, run_ffmpeg=fake_run_ffmpeg)

    assert len(samples) == 1
