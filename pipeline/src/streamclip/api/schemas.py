from datetime import datetime
from pathlib import PurePath

from pydantic import BaseModel, ConfigDict, computed_field

from streamclip.models import Platform, PublishStatus, ReviewStatus


class StreamerCreate(BaseModel):
    platform: Platform
    channel_id: str
    display_name: str


class StreamerUpdate(BaseModel):
    is_tracked: bool | None = None


class StreamerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: Platform
    channel_id: str
    display_name: str
    is_tracked: bool
    created_at: datetime


class ClipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    file_path: str
    trigger_offset_seconds: float
    clip_start_seconds: float
    clip_end_seconds: float
    highlight_score: float
    signal_breakdown: dict
    review_status: ReviewStatus
    publish_status: PublishStatus
    created_at: datetime
    reviewed_at: datetime | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def video_url(self) -> str:
        """Served by the API's /media/clips static mount (see api/app.py),
        which serves files directly out of the clips directory by basename."""
        return f"/media/clips/{PurePath(self.file_path).name}"


class CredentialStatusOut(BaseModel):
    twitch: bool
    youtube: bool
    kick: bool
    discord: bool
    post_for_me: bool
