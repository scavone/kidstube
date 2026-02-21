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


class HeartbeatResponse(BaseModel):
    remaining: int  # -1 if no limit


class CatalogResponse(BaseModel):
    videos: list[dict]
    has_more: bool
    total: int


class ChannelResponse(BaseModel):
    channel_name: str
    channel_id: Optional[str] = None
    handle: Optional[str] = None
    status: str
    category: Optional[str] = None
