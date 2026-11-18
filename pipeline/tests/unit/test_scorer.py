from datetime import datetime

import pytest

from streamclip.detection.audio_classifier import AudioEventScore
from streamclip.detection.chat_signals import ChatSignalScore
from streamclip.detection.scorer import HighlightScorer

T0 = datetime(2026, 11, 18, 12, 0, 0)


def chat(score: float, is_highlight: bool) -> ChatSignalScore:
    return ChatSignalScore(
        timestamp=T0, message_count=0, message_rate_per_second=0.0,
        rate_zscore=0.0, emote_density=0.0, score=score, is_highlight=is_highlight,
    )


def audio(confidence: float, is_highlight: bool) -> AudioEventScore:
    return AudioEventScore(
        offset_seconds=0.0, top_label="Laughter", top_label_score=confidence,
        event_confidence=confidence, is_highlight=is_highlight,
    )


def test_combine_weights_chat_and_audio():
    scorer = HighlightScorer(chat_weight=0.5, audio_weight=0.5)
    signal = scorer.combine(100.0, chat(0.8, True), audio(0.4, False))

    assert signal.combined_score == pytest.approx(0.6)
    assert signal.is_trigger is True  # chat alone is enough


def test_combine_handles_missing_signals():
    scorer = HighlightScorer()
    signal = scorer.combine(100.0, None, audio(0.9, True))

    assert signal.chat_score is None
    assert signal.combined_score == pytest.approx(0.45)
    assert signal.is_trigger is True


def test_no_trigger_produces_no_clip():
    scorer = HighlightScorer()
    signal = scorer.combine(100.0, chat(0.1, False), audio(0.1, False))

    assert scorer.process(signal) is None


def test_trigger_near_stream_start_clamps_window_to_zero():
    scorer = HighlightScorer(pre_roll_seconds=40.0, post_roll_seconds=10.0)
    signal = scorer.combine(20.0, chat(0.9, True), None)

    window = scorer.process(signal)

    assert window is not None
    assert window.start_seconds == 0.0
    assert window.end_seconds == 30.0
    assert window.trigger_offset_seconds == 20.0


def test_normal_trigger_produces_expected_pre_and_post_roll():
    scorer = HighlightScorer(pre_roll_seconds=40.0, post_roll_seconds=10.0)
    signal = scorer.combine(200.0, chat(0.9, True), None)

    window = scorer.process(signal)

    assert window.start_seconds == 160.0
    assert window.end_seconds == 210.0
    assert window.signal_breakdown["chat"] == pytest.approx(0.9)
    assert window.signal_breakdown["audio"] is None


def test_second_trigger_within_cooldown_is_suppressed():
    scorer = HighlightScorer(pre_roll_seconds=10.0, post_roll_seconds=10.0, trigger_cooldown_seconds=30.0)

    first = scorer.process(scorer.combine(100.0, chat(0.9, True), None))
    assert first is not None
    assert first.end_seconds == 110.0

    # second trigger at 115s is within 30s cooldown of the first clip's end (110s)
    second = scorer.process(scorer.combine(115.0, chat(0.9, True), None))
    assert second is None


def test_trigger_after_cooldown_produces_a_new_clip():
    scorer = HighlightScorer(pre_roll_seconds=10.0, post_roll_seconds=10.0, trigger_cooldown_seconds=30.0)

    first = scorer.process(scorer.combine(100.0, chat(0.9, True), None))
    assert first.end_seconds == 110.0

    # second trigger well past the cooldown window
    second = scorer.process(scorer.combine(160.0, chat(0.9, True), None))
    assert second is not None
    assert second.start_seconds == 150.0
    assert second.end_seconds == 170.0
