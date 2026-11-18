import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from streamclip.models import Clip, Platform, ReviewStatus, StreamSession, Streamer


async def test_create_streamer(db_session):
    streamer = Streamer(platform=Platform.TWITCH, channel_id="123", display_name="shroud")
    db_session.add(streamer)
    await db_session.commit()

    result = await db_session.execute(select(Streamer))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].display_name == "shroud"
    assert rows[0].is_tracked is True


async def test_duplicate_platform_channel_rejected(db_session):
    db_session.add(Streamer(platform=Platform.TWITCH, channel_id="123", display_name="a"))
    await db_session.commit()

    db_session.add(Streamer(platform=Platform.TWITCH, channel_id="123", display_name="b"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_session_and_clip_relationship(db_session):
    streamer = Streamer(platform=Platform.KICK, channel_id="abc", display_name="kicker")
    db_session.add(streamer)
    await db_session.flush()

    session = StreamSession(streamer_id=streamer.id, stream_url="https://kick.com/abc")
    db_session.add(session)
    await db_session.flush()

    clip = Clip(
        session_id=session.id,
        trigger_offset_seconds=120.0,
        clip_start_seconds=80.0,
        clip_end_seconds=130.0,
        highlight_score=0.91,
        signal_breakdown={"chat": 0.8, "audio": 0.95},
    )
    db_session.add(clip)
    await db_session.commit()

    result = await db_session.execute(select(Clip).where(Clip.session_id == session.id))
    stored = result.scalar_one()
    assert stored.review_status == ReviewStatus.PENDING
    assert stored.signal_breakdown["chat"] == 0.8
