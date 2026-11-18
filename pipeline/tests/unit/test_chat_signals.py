from datetime import datetime, timedelta

from streamclip.detection.chat_signals import ChatSignalDetector
from streamclip.platforms.base import ChatMessage

T0 = datetime(2026, 11, 18, 12, 0, 0)


def msg(author: str, text: str, seconds_after_t0: float, emotes=None) -> ChatMessage:
    return ChatMessage(
        author=author,
        text=text,
        timestamp=T0 + timedelta(seconds=seconds_after_t0),
        emotes=emotes or [],
    )


def test_quiet_chat_is_not_a_highlight():
    detector = ChatSignalDetector(window_seconds=10.0, baseline_window_seconds=60.0)
    for i in range(6):
        detector.add_message(msg("u", "hey", seconds_after_t0=i * 10))

    score = detector.score_at(T0 + timedelta(seconds=55))

    assert score.is_highlight is False
    assert score.rate_zscore < 1.0


def test_sudden_message_spike_is_flagged_as_highlight():
    detector = ChatSignalDetector(window_seconds=10.0, baseline_window_seconds=60.0, zscore_threshold=2.0)
    # steady baseline: ~1 message per 10s bucket for 50s
    for i in range(5):
        detector.add_message(msg("u", "chat is calm", seconds_after_t0=i * 10))

    # sudden burst of 20 messages in the most recent 10s window
    for i in range(20):
        detector.add_message(msg(f"user{i}", "that was crazy!!", seconds_after_t0=55 + i * 0.2))

    score = detector.score_at(T0 + timedelta(seconds=59))

    assert score.is_highlight is True
    assert score.rate_zscore > 2.0
    assert score.score > 0.5


def test_emote_density_alone_can_trigger_highlight_even_without_rate_spike():
    detector = ChatSignalDetector(
        window_seconds=10.0, baseline_window_seconds=60.0, emote_density_threshold=0.3
    )
    # same low message rate throughout, but the latest window is full of hype keywords
    for i in range(5):
        detector.add_message(msg("u", "just chatting", seconds_after_t0=i * 10))
    for i in range(5):
        detector.add_message(msg(f"u{i}", "POGGERS insane holy", seconds_after_t0=50 + i))

    score = detector.score_at(T0 + timedelta(seconds=59))

    assert score.emote_density == 1.0
    assert score.is_highlight is True


def test_old_messages_outside_baseline_window_are_evicted():
    detector = ChatSignalDetector(window_seconds=10.0, baseline_window_seconds=30.0)
    detector.add_message(msg("u", "ancient history", seconds_after_t0=0))

    score = detector.score_at(T0 + timedelta(seconds=1000))

    assert score.message_count == 0
    assert len(detector._messages) == 0


def test_emotes_list_counts_as_hype_even_without_keyword_text():
    detector = ChatSignalDetector(window_seconds=10.0, baseline_window_seconds=20.0)
    detector.add_message(msg("u", "just a normal message", seconds_after_t0=0, emotes=["PogChamp"]))

    score = detector.score_at(T0 + timedelta(seconds=1))

    assert score.emote_density == 1.0
