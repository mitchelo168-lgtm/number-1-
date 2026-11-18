import enum
from datetime import datetime

from sqlalchemy import JSON, Enum, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Platform(str, enum.Enum):
    TWITCH = "twitch"
    YOUTUBE = "youtube"
    KICK = "kick"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PublishStatus(str, enum.Enum):
    NOT_PUBLISHED = "not_published"
    QUEUED = "queued"
    PUBLISHED = "published"
    FAILED = "failed"


class Streamer(Base):
    __tablename__ = "streamers"
    __table_args__ = (UniqueConstraint("platform", "channel_id", name="uq_streamer_platform_channel"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform))
    channel_id: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(128))
    is_tracked: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    sessions: Mapped[list["StreamSession"]] = relationship(back_populates="streamer")


class StreamSession(Base):
    __tablename__ = "stream_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    streamer_id: Mapped[int] = mapped_column(ForeignKey("streamers.id"))
    started_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(default=None)
    stream_url: Mapped[str] = mapped_column(String(512))

    streamer: Mapped["Streamer"] = relationship(back_populates="sessions")
    chunks: Mapped[list["RecordingChunk"]] = relationship(back_populates="session")
    clips: Mapped[list["Clip"]] = relationship(back_populates="session")


class RecordingChunk(Base):
    __tablename__ = "recording_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("stream_sessions.id"))
    sequence: Mapped[int] = mapped_column()
    file_path: Mapped[str] = mapped_column(String(1024))
    started_at: Mapped[datetime] = mapped_column()
    duration_seconds: Mapped[float] = mapped_column(Float)

    session: Mapped["StreamSession"] = relationship(back_populates="chunks")


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("stream_sessions.id"))
    file_path: Mapped[str] = mapped_column(String(1024), default="")
    trigger_offset_seconds: Mapped[float] = mapped_column(Float)
    clip_start_seconds: Mapped[float] = mapped_column(Float)
    clip_end_seconds: Mapped[float] = mapped_column(Float)
    highlight_score: Mapped[float] = mapped_column(Float)
    signal_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING)
    publish_status: Mapped[PublishStatus] = mapped_column(Enum(PublishStatus), default=PublishStatus.NOT_PUBLISHED)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(default=None)

    session: Mapped["StreamSession"] = relationship(back_populates="clips")
