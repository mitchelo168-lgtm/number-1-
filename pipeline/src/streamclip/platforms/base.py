from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class LiveStatus:
    is_live: bool
    stream_url: str | None = None
    title: str | None = None
    started_at: datetime | None = None


@dataclass(frozen=True)
class ChatMessage:
    author: str
    text: str
    timestamp: datetime
    emotes: list[str] = field(default_factory=list)


class PlatformAdapter(ABC):
    """Uniform interface every streaming-platform integration implements.

    `channel_id` is whatever identifier the platform needs to look a channel
    up (Twitch login name, YouTube channel ID, Kick channel slug).
    """

    name: str

    @abstractmethod
    async def check_live(self, channel_id: str) -> LiveStatus: ...

    @abstractmethod
    def stream_chat(self, channel_id: str) -> AsyncIterator[ChatMessage]:
        """Async-iterate chat messages for a live channel until cancelled."""
        ...
