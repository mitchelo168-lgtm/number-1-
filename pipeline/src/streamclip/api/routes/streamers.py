from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from streamclip.api.deps import get_db
from streamclip.api.schemas import StreamerCreate, StreamerOut, StreamerUpdate
from streamclip.models import Streamer

router = APIRouter(prefix="/api/streamers", tags=["streamers"])


@router.get("", response_model=list[StreamerOut])
async def list_streamers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Streamer).order_by(Streamer.display_name))
    return result.scalars().all()


@router.post("", response_model=StreamerOut, status_code=201)
async def create_streamer(payload: StreamerCreate, db: AsyncSession = Depends(get_db)):
    streamer = Streamer(platform=payload.platform, channel_id=payload.channel_id, display_name=payload.display_name)
    db.add(streamer)
    await db.commit()
    await db.refresh(streamer)
    return streamer


@router.patch("/{streamer_id}", response_model=StreamerOut)
async def update_streamer(streamer_id: int, payload: StreamerUpdate, db: AsyncSession = Depends(get_db)):
    streamer = await db.get(Streamer, streamer_id)
    if streamer is None:
        raise HTTPException(status_code=404, detail="streamer not found")
    if payload.is_tracked is not None:
        streamer.is_tracked = payload.is_tracked
    await db.commit()
    await db.refresh(streamer)
    return streamer


@router.delete("/{streamer_id}", status_code=204)
async def delete_streamer(streamer_id: int, db: AsyncSession = Depends(get_db)):
    streamer = await db.get(Streamer, streamer_id)
    if streamer is None:
        raise HTTPException(status_code=404, detail="streamer not found")
    await db.delete(streamer)
    await db.commit()
