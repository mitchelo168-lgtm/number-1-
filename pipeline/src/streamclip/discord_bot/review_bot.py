"""The testable core of the Discord integration: what gets sent and what a
review decision does. Deliberately transport-agnostic — it depends on a
`send` callable rather than discord.py directly, so this logic can be fully
unit tested without a real bot/gateway connection. `bot.py` wires this to an
actual discord.py `commands.Bot`.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker

from streamclip.models import Clip
from streamclip.review_service import set_review_status


@dataclass(frozen=True)
class ReviewMessage:
    channel_id: int
    content: str
    file_path: str | None = None
    clip_id: int | None = None  # set when the message should carry approve/reject actions


SendFn = Callable[[ReviewMessage], Awaitable[None]]


class DiscordReviewBot:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        send: SendFn,
        review_channel_id: int,
        on_approved: Callable[[Clip], Awaitable[None]] | None = None,
    ):
        self._session_factory = session_factory
        self._send = send
        self._review_channel_id = review_channel_id
        self._on_approved = on_approved

    async def notify_live(self, streamer_display_name: str, platform: str) -> None:
        await self._send(
            ReviewMessage(
                channel_id=self._review_channel_id,
                content=f"\U0001f534 **{streamer_display_name}** just went live on {platform}.",
            )
        )

    async def notify_clip_ready(self, clip: Clip, streamer_display_name: str) -> None:
        await self._send(
            ReviewMessage(
                channel_id=self._review_channel_id,
                content=(
                    f"\U0001f3ac New clip from **{streamer_display_name}** "
                    f"(score {clip.highlight_score:.2f}) — approve or reject:"
                ),
                file_path=clip.file_path,
                clip_id=clip.id,
            )
        )

    async def handle_review_decision(self, clip_id: int, approved: bool) -> Clip:
        return await set_review_status(self._session_factory, clip_id, approved, self._on_approved)
