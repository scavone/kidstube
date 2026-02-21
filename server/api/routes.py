"""FastAPI route definitions — JSON API for the tvOS app.

All endpoints require API key authentication (Bearer token).
The tvOS app passes child_id on every request to identify the active profile.
"""

import logging
import re
import time

from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from api.auth import verify_api_key
from api.models import (
    VideoRequestBody,
    HeartbeatBody,
    CreateChildBody,
    UpdateChildBody,
    HeartbeatResponse,
    VideoStatusResponse,
    StreamUrlResponse,
    TimeStatusResponse,
    ScheduleStatusResponse,
)
from utils import get_today_str, get_day_utc_bounds, is_within_schedule, format_time_12h

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", dependencies=[Depends(verify_api_key)])
public_router = APIRouter(prefix="/api")

VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")

# Injected by main.py at startup
video_store = None
invidious_client = None
notify_callback = None
config = None

# Heartbeat dedup: (child_id, video_id) -> monotonic timestamp
_last_heartbeat: dict[tuple[int, str], float] = {}
_HEARTBEAT_MIN_INTERVAL = 10
_HEARTBEAT_EVICT_AGE = 120
_heartbeat_last_cleanup: float = 0.0


def setup(store, inv_client, cfg, notify_cb=None):
    """Called by main.py to inject dependencies."""
    global video_store, invidious_client, config, notify_callback
    video_store = store
    invidious_client = inv_client
    config = cfg
    notify_callback = notify_cb


# ── Profiles ────────────────────────────────────────────────────────

@router.get("/profiles")
async def list_profiles():
    children = video_store.get_children()
    return {"profiles": children}


@router.post("/profiles")
async def create_profile(body: CreateChildBody):
    child = video_store.add_child(body.name, body.avatar)
    if not child:
        raise HTTPException(status_code=409, detail="A child with that name already exists")
    # Set default daily limit from config
    default_limit = config.watch_limits.daily_limit_minutes
    video_store.set_child_setting(child["id"], "daily_limit_minutes", str(default_limit))
    return child


@router.put("/profiles/{child_id}")
async def update_profile(child_id: int, body: UpdateChildBody):
    if body.name is None and body.avatar is None:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")
    child = video_store.update_child(child_id, name=body.name, avatar=body.avatar)
    if not child:
        existing = video_store.get_child(child_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Child not found")
        raise HTTPException(status_code=409, detail="A child with that name already exists")
    return child


@router.delete("/profiles/{child_id}")
async def delete_profile(child_id: int):
    video_store.delete_avatar(child_id)
    if not video_store.remove_child(child_id):
        raise HTTPException(status_code=404, detail="Child not found")
    return {"status": "deleted", "child_id": child_id}


@router.post("/profiles/{child_id}/avatar")
async def upload_avatar(child_id: int, file: UploadFile = File(...)):
    child = video_store.get_child(child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:  # 5 MB limit
        raise HTTPException(status_code=400, detail="File too large (max 5 MB)")

    if not video_store.save_avatar(child_id, contents):
        raise HTTPException(status_code=500, detail="Failed to save avatar")

    return {"status": "uploaded", "child_id": child_id}


@public_router.get("/profiles/{child_id}/avatar")
async def get_avatar(child_id: int):
    path = video_store.get_avatar_path(child_id)
    if not path:
        raise HTTPException(status_code=404, detail="No avatar photo found")
    return FileResponse(path, media_type="image/jpeg")


# ── Search ──────────────────────────────────────────────────────────

@router.get("/search")
async def search_videos(
    q: str = Query(..., min_length=1, max_length=200),
    child_id: int = Query(..., gt=0),
):
    # Verify child exists
    child = video_store.get_child(child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Block queries containing filtered words
    word_filters = video_store.get_word_filters_set()
    if word_filters:
        word_patterns = [
            re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE)
            for w in word_filters
        ]
        if any(p.search(q) for p in word_patterns):
            video_store.record_search(q, child_id, 0)
            return {"results": [], "query": q}
    else:
        word_patterns = []

    results = await invidious_client.search(q, max_results=config.invidious.search_max_results)

    # Filter blocked channels
    blocked = video_store.get_blocked_channels_set()
    if blocked:
        results = [r for r in results if r.get("channel_name", "").lower() not in blocked]

    # Filter blocked words in titles
    if word_patterns:
        results = [
            r for r in results
            if not any(p.search(r.get("title", "")) for p in word_patterns)
        ]

    # Annotate each result with the child's access status
    for r in results:
        vid = r.get("video_id", "")
        status = video_store.get_video_status(child_id, vid)
        r["access_status"] = status  # None, 'pending', 'approved', 'denied'

    video_store.record_search(q, child_id, len(results))
    return {"results": results, "query": q}


# ── Request Video ───────────────────────────────────────────────────

@router.post("/request")
async def request_video(body: VideoRequestBody):
    child = video_store.get_child(body.child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    if not VIDEO_ID_RE.match(body.video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID format")

    # Ensure video metadata exists in our DB
    video = video_store.get_video(body.video_id)
    if not video:
        metadata = await invidious_client.get_video(body.video_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="Video not found on Invidious")
        video = video_store.add_video(
            video_id=metadata["video_id"],
            title=metadata["title"],
            channel_name=metadata["channel_name"],
            channel_id=metadata.get("channel_id"),
            thumbnail_url=metadata.get("thumbnail_url"),
            duration=metadata.get("duration"),
        )

    status = video_store.request_video(body.child_id, body.video_id)

    # If pending, notify parent via Telegram
    if status == "pending" and notify_callback:
        await notify_callback(child, video)

    # Normalize auto_approved to approved for the client
    if status == "auto_approved":
        status = "approved"

    return {"status": status, "video_id": body.video_id, "child_id": body.child_id}


# ── Status Polling ──────────────────────────────────────────────────

@router.get("/status/{video_id}")
async def get_status(
    video_id: str,
    child_id: int = Query(..., gt=0),
):
    if not VIDEO_ID_RE.match(video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID format")

    status = video_store.get_video_status(child_id, video_id)
    return VideoStatusResponse(status=status or "not_found")


# ── Stream URL ──────────────────────────────────────────────────────

@router.get("/stream/{video_id}")
async def get_stream(
    video_id: str,
    child_id: int = Query(..., gt=0),
):
    if not VIDEO_ID_RE.match(video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID format")

    # Verify child has access
    status = video_store.get_video_status(child_id, video_id)
    if status != "approved":
        raise HTTPException(status_code=403, detail="Video not approved for this child")

    # Fetch fresh stream URL (they expire)
    url = await invidious_client.get_stream_url(video_id)
    if not url:
        raise HTTPException(status_code=502, detail="Could not resolve stream URL from Invidious")

    return StreamUrlResponse(url=url)


# ── Catalog ─────────────────────────────────────────────────────────

@router.get("/catalog")
async def get_catalog(
    child_id: int = Query(..., gt=0),
    category: str = Query("", max_length=10),
    channel: str = Query("", max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
):
    child = video_store.get_child(child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    videos, total = video_store.get_approved_videos(
        child_id,
        category=category or None,
        channel=channel or None,
        offset=offset,
        limit=limit,
    )

    return {
        "videos": videos,
        "has_more": offset + limit < total,
        "total": total,
    }


# ── Channels ────────────────────────────────────────────────────────

@router.get("/channels")
async def list_channels():
    channels = video_store.get_channels(status="allowed")
    return {"channels": channels}


# ── Watch Heartbeat ─────────────────────────────────────────────────

@router.post("/watch-heartbeat")
async def watch_heartbeat(body: HeartbeatBody):
    global _heartbeat_last_cleanup

    if not VIDEO_ID_RE.match(body.video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID format")

    child = video_store.get_child(body.child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Verify video is approved for this child
    status = video_store.get_video_status(body.child_id, body.video_id)
    if status != "approved":
        raise HTTPException(status_code=400, detail="Video not approved")

    # Check schedule window
    tz = config.watch_limits.timezone
    schedule_start = video_store.get_child_setting(body.child_id, "schedule_start", "")
    schedule_end = video_store.get_child_setting(body.child_id, "schedule_end", "")
    if schedule_start or schedule_end:
        allowed, _ = is_within_schedule(schedule_start, schedule_end, tz)
        if not allowed:
            return HeartbeatResponse(remaining=-2)  # -2 = outside schedule

    # Dedup rapid heartbeats
    hb_key = (body.child_id, body.video_id)
    now = time.monotonic()
    seconds = body.seconds
    last = _last_heartbeat.get(hb_key, 0.0)
    if last and (now - last) < _HEARTBEAT_MIN_INTERVAL:
        seconds = 0
    _last_heartbeat[hb_key] = now

    # Evict stale heartbeat entries
    if now - _heartbeat_last_cleanup > _HEARTBEAT_EVICT_AGE:
        _heartbeat_last_cleanup = now
        stale = [k for k, t in _last_heartbeat.items() if now - t > _HEARTBEAT_EVICT_AGE]
        for k in stale:
            del _last_heartbeat[k]

    if seconds > 0:
        video_store.record_watch_seconds(body.video_id, body.child_id, seconds)

    # Calculate remaining time
    remaining = _get_remaining_seconds(body.child_id)
    return HeartbeatResponse(remaining=remaining)


# ── Time Status ─────────────────────────────────────────────────────

@router.get("/time-status")
async def time_status(child_id: int = Query(..., gt=0)):
    child = video_store.get_child(child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    tz = config.watch_limits.timezone
    limit_min = int(video_store.get_child_setting(
        child_id, "daily_limit_minutes",
        str(config.watch_limits.daily_limit_minutes),
    ))
    today = get_today_str(tz)
    bounds = get_day_utc_bounds(today, tz)
    used_min = video_store.get_daily_watch_minutes(child_id, today, utc_bounds=bounds)
    remaining_min = max(0.0, limit_min - used_min)

    return TimeStatusResponse(
        limit_min=limit_min,
        used_min=round(used_min, 1),
        remaining_min=round(remaining_min, 1),
        remaining_sec=int(remaining_min * 60),
        exceeded=remaining_min <= 0,
    )


# ── Schedule Status ─────────────────────────────────────────────────

@router.get("/schedule-status")
async def schedule_status(child_id: int = Query(..., gt=0)):
    child = video_store.get_child(child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    tz = config.watch_limits.timezone
    start = video_store.get_child_setting(child_id, "schedule_start", "")
    end = video_store.get_child_setting(child_id, "schedule_end", "")

    if not start and not end:
        return ScheduleStatusResponse(
            allowed=True, unlock_time="", start="", end=""
        )

    allowed, unlock_time = is_within_schedule(start, end, tz)
    return ScheduleStatusResponse(
        allowed=allowed,
        unlock_time=unlock_time,
        start=format_time_12h(start) if start else "midnight",
        end=format_time_12h(end) if end else "midnight",
    )


# ── Helpers ─────────────────────────────────────────────────────────

def _get_remaining_seconds(child_id: int) -> int:
    """Calculate remaining watch seconds for a child today. Returns -1 if no limit."""
    tz = config.watch_limits.timezone
    limit_str = video_store.get_child_setting(child_id, "daily_limit_minutes", "")
    if not limit_str:
        limit_min = config.watch_limits.daily_limit_minutes
    else:
        limit_min = int(limit_str)

    if limit_min == 0:
        return -1

    today = get_today_str(tz)
    bounds = get_day_utc_bounds(today, tz)
    used_min = video_store.get_daily_watch_minutes(child_id, today, utc_bounds=bounds)
    remaining = max(0.0, limit_min - used_min)
    return int(remaining * 60)
