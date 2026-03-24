"""Pydantic request/response models for the API."""

from pydantic import BaseModel, Field
from typing import Optional


# ── Requests ────────────────────────────────────────────────────────

class VideoRequestBody(BaseModel):
    video_id: str = Field(..., min_length=1, max_length=20)
    child_id: int = Field(..., gt=0)


class HeartbeatBody(BaseModel):
    video_id: str = Field(..., min_length=1, max_length=20)
    child_id: int = Field(..., gt=0)
    seconds: int = Field(..., ge=0, le=60)


class CreateChildBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    avatar: str = Field(default="👦", max_length=10)


class UpdateChildBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    avatar: Optional[str] = Field(default=None, max_length=10)


class WatchPositionBody(BaseModel):
    video_id: str = Field(..., min_length=1, max_length=20)
    child_id: int = Field(..., gt=0)
    position: int = Field(..., ge=0)
    duration: int = Field(..., ge=0)


class WatchStatusBody(BaseModel):
    video_id: str = Field(..., min_length=1, max_length=20)
    child_id: int = Field(..., gt=0)
    status: str = Field(..., pattern=r"^(watched|unwatched)$")


class ImportStarterChannelsBody(BaseModel):
    handles: list[str] = Field(..., min_length=1)
    child_id: int = Field(..., gt=0)


class ChannelRequestBody(BaseModel):
    child_id: int = Field(..., gt=0)
    channel_id: str = Field(..., pattern=r"^UC[a-zA-Z0-9_-]{22}$")


# ── Responses ───────────────────────────────────────────────────────

class ChildProfileResponse(BaseModel):
    id: int
    name: str
    avatar: str
    created_at: str


class VideoResponse(BaseModel):
    video_id: str
    title: str
    channel_name: str
    channel_id: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[int] = None
    category: Optional[str] = None


class VideoStatusResponse(BaseModel):
    status: str  # pending, approved, denied, not_found


class StreamUrlResponse(BaseModel):
    url: str
    session_id: Optional[str] = None


class TimeStatusResponse(BaseModel):
    limit_min: int
    used_min: float
    remaining_min: float
    remaining_sec: int
    exceeded: bool


class ScheduleStatusResponse(BaseModel):
    allowed: bool
    unlock_time: str
    start: str
    end: str
    minutes_remaining: int  # -1 if no end time / no schedule


class HeartbeatResponse(BaseModel):
    remaining: int  # -1 if no limit


class CatalogResponse(BaseModel):
    videos: list[dict]
    has_more: bool
    total: int
    status_counts: Optional[dict] = None


class ChannelRequestResponse(BaseModel):
    status: str
    channel_id: str
    child_id: int
    channel_name: str


class ChannelResponse(BaseModel):
    channel_name: str
    channel_id: Optional[str] = None
    handle: Optional[str] = None
    status: str
    category: Optional[str] = None


# ── Time Request ──────────────────────────────────────────────────

class TimeRequestBody(BaseModel):
    child_id: int = Field(..., gt=0)
    video_id: Optional[str] = Field(default=None, max_length=20)


class TimeRequestResponse(BaseModel):
    status: str  # pending, granted, denied, already_pending
    bonus_minutes: int = 0


class TimeRequestStatusResponse(BaseModel):
    status: str  # none, pending, granted, denied
    bonus_minutes: int = 0


# ── Channels Home ────────────────────────────────────────────────

class LatestVideoResponse(BaseModel):
    video_id: str
    title: str
    thumbnail_url: Optional[str] = None
    duration: Optional[int] = None
    published_at: Optional[int] = None


class ChannelHomeItem(BaseModel):
    channel_name: str
    channel_id: Optional[str] = None
    handle: Optional[str] = None
    category: Optional[str] = None
    thumbnail_url: Optional[str] = None
    banner_url: Optional[str] = None
    latest_video: Optional[LatestVideoResponse] = None


class ChannelsHomeResponse(BaseModel):
    channels: list[ChannelHomeItem]
