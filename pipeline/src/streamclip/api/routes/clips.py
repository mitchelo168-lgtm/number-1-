from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from streamclip.api.deps import get_db, get_session_factory
from streamclip.api.schemas import ClipOut
from streamclip.models import Clip, ReviewStatus
from streamclip.review_service import set_review_status

router = APIRouter(prefix="/api/clips", tags=["clips"])


@router.get("", response_model=list[ClipOut])
async def list_clips(review_status: ReviewStatus | None = None, db: AsyncSession = Depends(get_db)):
    query = select(Clip).order_by(Clip.created_at.desc())
    if review_status is not None:
        query = query.where(Clip.review_status == review_status)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{clip_id}/approve", response_model=ClipOut)
async def approve_clip(clip_id: int, session_factory: async_sessionmaker = Depends(get_session_factory)):
    try:
        return await set_review_status(session_factory, clip_id, approved=True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{clip_id}/reject", response_model=ClipOut)
async def reject_clip(clip_id: int, session_factory: async_sessionmaker = Depends(get_session_factory)):
    try:
        return await set_review_status(session_factory, clip_id, approved=False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
