"""Combines chat + audio highlight signals into clip-worthy trigger windows.

Mirrors what the source video describes: once something is flagged, the
resulting clip starts `pre_roll_seconds` *before* the trigger moment (to
catch the build-up) and runs `post_roll_seconds` past it. A
`trigger_cooldown_seconds` window after each clip suppresses near-duplicate
clips from a single sustained moment (e.g. a laugh that keeps a chat-rate
spike alive for 15 seconds shouldn't produce five overlapping clips).
"""

from dataclasses import dataclass

from streamclip.detection.audio_classifier import AudioEventScore
from streamclip.detection.chat_signals import ChatSignalScore


@dataclass(frozen=True)
class CombinedSignal:
    offset_seconds: float
    chat_score: float | None
    audio_score: float | None
    combined_score: float
    is_trigger: bool


@dataclass(frozen=True)
class ClipWindow:
    trigger_offset_seconds: float
    start_seconds: float
    end_seconds: float
    highlight_score: float
    signal_breakdown: dict


class HighlightScorer:
    def __init__(
        self,
        pre_roll_seconds: float = 40.0,
        post_roll_seconds: float = 10.0,
        trigger_cooldown_seconds: float = 30.0,
        chat_weight: float = 0.5,
        audio_weight: float = 0.5,
    ):
        self._pre_roll = pre_roll_seconds
        self._post_roll = post_roll_seconds
        self._cooldown = trigger_cooldown_seconds
        self._chat_weight = chat_weight
        self._audio_weight = audio_weight
        self._last_clip_end: float | None = None

    def combine(
        self,
        offset_seconds: float,
        chat_score: ChatSignalScore | None,
        audio_score: AudioEventScore | None,
    ) -> CombinedSignal:
        chat_value = chat_score.score if chat_score is not None else None
        audio_value = audio_score.event_confidence if audio_score is not None else None

        combined = self._chat_weight * (chat_value or 0.0) + self._audio_weight * (audio_value or 0.0)
        is_trigger = bool((chat_score and chat_score.is_highlight) or (audio_score and audio_score.is_highlight))

        return CombinedSignal(
            offset_seconds=offset_seconds,
            chat_score=chat_value,
            audio_score=audio_value,
            combined_score=combined,
            is_trigger=is_trigger,
        )

    def process(self, signal: CombinedSignal) -> ClipWindow | None:
        if not signal.is_trigger:
            return None
        if self._last_clip_end is not None and signal.offset_seconds < self._last_clip_end + self._cooldown:
            return None

        start = max(0.0, signal.offset_seconds - self._pre_roll)
        end = signal.offset_seconds + self._post_roll
        self._last_clip_end = end

        return ClipWindow(
            trigger_offset_seconds=signal.offset_seconds,
            start_seconds=start,
            end_seconds=end,
            highlight_score=signal.combined_score,
            signal_breakdown={"chat": signal.chat_score, "audio": signal.audio_score},
        )
