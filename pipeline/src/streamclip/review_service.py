"""Shared clip-review logic used by both the Discord bot and the GUI's REST
API, so "approve" means exactly the same thing regardless of which surface
triggered it.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker

from streamclip.models import Clip, ReviewStatus


async def set_review_status(
    session_factory: async_sessionmaker,
    clip_id: int,
    approved: bool,
    on_approved: Callable[[Clip], Awaitable[None]] | None = None,
) -> Clip:
    async with session_factory() as session:
        clip = await session.get(Clip, clip_id)
        if clip is None:
            raise ValueError(f"no clip with id {clip_id}")

        clip.review_status = ReviewStatus.APPROVED if approved else ReviewStatus.REJECTED
        clip.reviewed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(clip)

    if approved and on_approved:
        await on_approved(clip)

    return clip
