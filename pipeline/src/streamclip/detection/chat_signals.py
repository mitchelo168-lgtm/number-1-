"""Chat-based highlight signal: message-rate spikes + hype-keyword/emote bursts.

Pure logic, no I/O: callers feed it `ChatMessage`s as they arrive (from any
platform adapter's `stream_chat`) and ask for a score at a point in time.
"""

import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from streamclip.platforms.base import ChatMessage

DEFAULT_HYPE_KEYWORDS = frozenset(
    {
        "lol", "lmao", "lmfao", "omg", "wtf", "insane", "poggers", "pog",
        "pogchamp", "no way", "holy", "clip it", "clip that", "wow", "crazy",
    }
)


@dataclass(frozen=True)
class ChatSignalScore:
    timestamp: datetime
    message_count: int
    message_rate_per_second: float
    rate_zscore: float
    emote_density: float
    score: float
    is_highlight: bool


class ChatSignalDetector:
    def __init__(
        self,
        window_seconds: float = 10.0,
        baseline_window_seconds: float = 120.0,
        hype_keywords: frozenset[str] = DEFAULT_HYPE_KEYWORDS,
        zscore_threshold: float = 2.5,
        emote_density_threshold: float = 0.3,
    ):
        if baseline_window_seconds < window_seconds:
            raise ValueError("baseline_window_seconds must be >= window_seconds")
        self._window = window_seconds
        self._baseline_window = baseline_window_seconds
        self._hype_keywords = hype_keywords
        self._zscore_threshold = zscore_threshold
        self._emote_density_threshold = emote_density_threshold
        self._messages: deque[ChatMessage] = deque()

    def add_message(self, message: ChatMessage) -> None:
        self._messages.append(message)

    def _evict_older_than(self, cutoff: datetime) -> None:
        while self._messages and self._messages[0].timestamp < cutoff:
            self._messages.popleft()

    def _is_hype(self, message: ChatMessage) -> bool:
        if message.emotes:
            return True
        text = message.text.lower()
        return any(keyword in text for keyword in self._hype_keywords)

    def score_at(self, now: datetime) -> ChatSignalScore:
        cutoff = now - timedelta(seconds=self._baseline_window)
        self._evict_older_than(cutoff)

        num_buckets = max(1, int(self._baseline_window // self._window))
        buckets = [0] * num_buckets
        current_bucket_messages: list[ChatMessage] = []

        for message in self._messages:
            age = (now - message.timestamp).total_seconds()
            if age < 0:
                continue
            idx = int(age // self._window)
            if 0 <= idx < num_buckets:
                buckets[idx] += 1
                if idx == 0:
                    current_bucket_messages.append(message)

        current = buckets[0]
        history = buckets[1:]
        mean = sum(history) / len(history) if history else 0.0
        variance = sum((x - mean) ** 2 for x in history) / len(history) if history else 0.0
        std = math.sqrt(variance)

        if std > 0:
            zscore = (current - mean) / std
        elif current > mean:
            zscore = self._zscore_threshold * 4  # unambiguous spike vs a flat/silent baseline
        else:
            zscore = 0.0

        emote_density = (
            sum(1 for m in current_bucket_messages if self._is_hype(m)) / len(current_bucket_messages)
            if current_bucket_messages
            else 0.0
        )

        normalized_rate = max(0.0, min(zscore / (self._zscore_threshold * 2), 1.0))
        score = max(0.0, min(normalized_rate * 0.7 + emote_density * 0.3, 1.0))

        is_highlight = zscore >= self._zscore_threshold or emote_density >= self._emote_density_threshold

        return ChatSignalScore(
            timestamp=now,
            message_count=current,
            message_rate_per_second=current / self._window,
            rate_zscore=zscore,
            emote_density=emote_density,
            score=score,
            is_highlight=is_highlight,
        )
