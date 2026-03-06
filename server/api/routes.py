"""FastAPI route definitions — JSON API for the tvOS app.

All endpoints require API key authentication (Bearer token).
The tvOS app passes child_id on every request to identify the active profile.
"""

import asyncio
import logging
import math
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path

import yaml

from fastapi import APIRouter, Depends, Query, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, Response, StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.auth import verify_api_key
from api.models import (
    VideoRequestBody,
    HeartbeatBody,
    CreateChildBody,
    UpdateChildBody,
    ImportStarterChannelsBody,
    HeartbeatResponse,
    VideoStatusResponse,
    StreamUrlResponse,
    TimeStatusResponse,
    ScheduleStatusResponse,
)
from utils import get_today_str, get_day_utc_bounds, is_within_schedule, format_time_12h

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

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

# Notification dedup: (child_id, video_id) -> monotonic timestamp
_last_notification: dict[tuple[int, str], float] = {}
_NOTIFICATION_MIN_INTERVAL = 60  # seconds

# Server-side ffmpeg HLS muxing for HQ adaptive streams
_FFMPEG_PATH = shutil.which("ffmpeg")

# Active HLS sessions: session_id -> {dir, process, video_id, created_at}
_hls_sessions: dict[str, dict] = {}


def _get_external_base_url(request: Request) -> str:
    """Get the external base URL for constructing client-facing URLs.

    Uses BRG_BASE_URL config if set, otherwise falls back to request.base_url.
    """
    if config and config.web.base_url:
        return config.web.base_url.rstrip("/")
    return str(request.base_url).rstrip("/")
_HLS_SESSION_MAX_AGE = 7200  # 2 hours
_HLS_SEGMENT_SECONDS = 2  # Short segments for faster initial playback


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
@limiter.limit("30/minute")
async def search_videos(
    request: Request,
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

    # Filter videos flagged as not family-friendly
    results = [r for r in results if r.get("is_family_friendly", True) is not False]

    # Filter blocked channels (per-child)
    blocked = video_store.get_blocked_channels_set(child_id)
    if blocked:
        results = [r for r in results if r.get("channel_name", "").lower() not in blocked]

    # Filter blocked words in titles
    if word_patterns:
        results = [
            r for r in results
            if not any(p.search(r.get("title", "")) for p in word_patterns)
        ]

    # Annotate each result with the child's access status.
    # For allowed-channel videos without an existing record, auto-approve them
    # so the child sees "Watch" instead of "Request".
    for r in results:
        vid = r.get("video_id", "")
        status = video_store.get_video_status(child_id, vid)
        if status is None:
            ch_name = r.get("channel_name", "")
            if ch_name and video_store.is_channel_allowed(child_id, ch_name):
                video_store.add_video(
                    video_id=vid,
                    title=r.get("title", ""),
                    channel_name=ch_name,
                    channel_id=r.get("channel_id"),
                    thumbnail_url=r.get("thumbnail_url"),
                    duration=r.get("duration"),
                    published_at=r.get("published"),
                )
                video_store.request_video(child_id, vid)  # auto-approves
                status = "approved"
        r["access_status"] = status  # None, 'pending', 'approved', 'denied'

    video_store.record_search(q, child_id, len(results))
    return {"results": results, "query": q}


# ── Request Video ───────────────────────────────────────────────────

@router.post("/request")
@limiter.limit("20/minute")
async def request_video(request: Request, body: VideoRequestBody):
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
            published_at=metadata.get("published"),
        )

    status = video_store.request_video(body.child_id, body.video_id)

    # If pending, notify parent via Telegram (with dedup)
    if status == "pending" and notify_callback:
        notif_key = (body.child_id, body.video_id)
        now = time.monotonic()
        last_notif = _last_notification.get(notif_key, 0.0)
        if now - last_notif >= _NOTIFICATION_MIN_INTERVAL:
            _last_notification[notif_key] = now
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
    request: Request,
    child_id: int = Query(..., gt=0),
):
    if not VIDEO_ID_RE.match(video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID format")

    # Verify child has access
    status = video_store.get_video_status(child_id, video_id)
    if status != "approved":
        raise HTTPException(status_code=403, detail="Video not approved for this child")

    # Fetch video metadata once — used for all quality tiers
    video = await invidious_client.get_video(video_id)
    if not video:
        raise HTTPException(status_code=502, detail="Could not resolve video from Invidious")

    # 1. Prefer HLS via ffmpeg adaptive muxing (up to 1080p)
    if _FFMPEG_PATH:
        adaptive = video.get("adaptive_formats", [])
        # Per-child language overrides the global config
        child_lang = video_store.get_child_setting(child_id, "preferred_language", "")
        preferred_lang = child_lang or config.preferred_audio_lang
        pair = invidious_client.pick_best_adaptive_pair(
            adaptive, preferred_lang=preferred_lang
        )
        if pair:
            duration = video.get("duration", 0)
            session_id = await _start_hls_session(video_id, pair, duration=duration)
            base = _get_external_base_url(request)
            hls_url = f"{base}/api/hls/{session_id}/index.m3u8"
            logger.info("Directing %s to HLS session %s (url=%s)", video_id, session_id, hls_url)
            return StreamUrlResponse(url=hls_url, session_id=session_id)

    # 2. Try HLS URL from Invidious (if instance provides it)
    hls_url = video.get("hls_url")
    if hls_url:
        return StreamUrlResponse(url=hls_url)

    # 3. Fall back to best progressive MP4
    streams = video.get("format_streams", [])
    url = invidious_client._pick_best_stream(streams)
    if not url:
        raise HTTPException(status_code=502, detail="No playable streams found")

    return StreamUrlResponse(url=url)


# ── HLS Serving (ffmpeg adaptive mux) ─────────────────────────────

@public_router.get("/hls/{session_id}/{filename}")
async def serve_hls(session_id: str, filename: str):
    """Serve HLS playlist and segment files for an active muxing session."""
    # Evict expired sessions periodically
    _cleanup_expired_sessions()

    session = _hls_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = os.path.join(session["dir"], filename)

    if filename.endswith(".m3u8"):
        duration = session.get("duration", 0)
        if duration > 0:
            # Synthetic VOD playlist: AVPlayer sees total duration + scrubber
            content = _generate_vod_playlist(duration)
            return Response(
                content=content,
                media_type="application/vnd.apple.mpegurl",
                headers={"Cache-Control": "no-cache, no-store"},
            )
        # Fall back to ffmpeg's playlist if duration unknown
        for _ in range(20):
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                break
            await asyncio.sleep(0.5)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Playlist not ready")
        return FileResponse(
            filepath,
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-cache, no-store"},
        )

    if filename.endswith(".ts"):
        proc = session.get("process")

        # If segment doesn't exist, check if we need to restart ffmpeg
        if not (os.path.exists(filepath) and os.path.getsize(filepath) > 0):
            try:
                seg_index = int(filename.replace("seg_", "").replace(".ts", ""))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid segment name")
            highest = _highest_segment_on_disk(session["dir"])
            ffmpeg_start = session.get("ffmpeg_start_seg", 0)
            need_restart = (
                proc and proc.returncode is None and (
                    seg_index > highest + 3          # forward seek
                    or seg_index < ffmpeg_start      # backward seek (gap)
                )
            )
            if need_restart:
                await _restart_ffmpeg_at(session_id, seg_index)
                proc = session["process"]

        # Wait for ffmpeg to create the segment
        for _ in range(60):  # 30 seconds max
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                break
            if proc and proc.returncode is not None:
                raise HTTPException(status_code=404, detail="Segment not available")
            await asyncio.sleep(0.5)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Segment not ready")
        return FileResponse(filepath, media_type="video/mp2t")

    raise HTTPException(status_code=400, detail="Unsupported file type")


@router.delete("/hls/{session_id}")
async def delete_hls_session(session_id: str):
    """Kill ffmpeg and clean up an HLS session immediately.

    Called by the tvOS app when the player is dismissed so we don't
    leave ffmpeg running for up to 2 hours.
    """
    if session_id not in _hls_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    _cleanup_hls_session(session_id)
    return {"status": "deleted", "session_id": session_id}


# ── Catalog ─────────────────────────────────────────────────────────

_CATALOG_SORT_OPTIONS = {"newest", "oldest", "title", "channel"}


@router.get("/catalog")
async def get_catalog(
    child_id: int = Query(..., gt=0),
    category: str = Query("", max_length=10),
    channel: str = Query("", max_length=200),
    sort_by: str = Query("newest", max_length=20),
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
):
    child = video_store.get_child(child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    if sort_by not in _CATALOG_SORT_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by. Options: {', '.join(sorted(_CATALOG_SORT_OPTIONS))}",
        )

    videos, total = video_store.get_approved_videos(
        child_id,
        category=category or None,
        channel=channel or None,
        sort_by=sort_by,
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
async def list_channels(child_id: int = Query(..., gt=0)):
    child = video_store.get_child(child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    channels = video_store.get_channels(child_id, status="allowed")
    return {"channels": channels}


# ── Starter Channels (Onboarding) ──────────────────────────────────

_starter_channels_cache: dict | None = None


def _load_starter_channels() -> dict:
    """Load starter channels from the bundled YAML file. Cached after first load."""
    global _starter_channels_cache
    if _starter_channels_cache is not None:
        return _starter_channels_cache

    yaml_path = Path(__file__).resolve().parent.parent / "starter_channels.yaml"
    if not yaml_path.exists():
        _starter_channels_cache = {}
        return _starter_channels_cache

    with open(yaml_path) as f:
        data = yaml.safe_load(f) or {}
    _starter_channels_cache = data
    return _starter_channels_cache


@router.get("/onboarding/starter-channels")
async def get_starter_channels(child_id: int = Query(0, ge=0)):
    """Return the curated starter channel list, organized by category.

    If child_id is provided, each channel is annotated with whether
    it's already imported for that child.
    """
    data = _load_starter_channels()

    imported_handles: set[str] = set()
    if child_id > 0:
        channels = video_store.get_channels(child_id)
        for ch in channels:
            h = ch.get("handle", "")
            if h:
                imported_handles.add(h.lower())

    result = {}
    for category, channels_list in data.items():
        items = []
        for ch in channels_list:
            handle = ch.get("handle", "")
            items.append({
                **ch,
                "imported": handle.lower() in imported_handles if handle else False,
            })
        result[category] = items

    return {"categories": result}


@router.post("/onboarding/import")
async def import_starter_channels(body: ImportStarterChannelsBody):
    """Import selected starter channels for a child.

    Accepts a list of @handles. Adds them to the child's allowed channels
    with lazy channel_id resolution (no network calls).
    """
    child = video_store.get_child(body.child_id)
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    data = _load_starter_channels()

    # Build lookup of handle -> channel info
    handle_lookup: dict[str, dict] = {}
    for category, channels_list in data.items():
        for ch in channels_list:
            h = ch.get("handle", "")
            if h:
                handle_lookup[h.lower()] = {**ch, "category_key": category}

    imported = []
    for handle in body.handles:
        info = handle_lookup.get(handle.lower())
        if not info:
            continue
        # Map category key to edu/fun
        cat_key = info.get("category_key", "fun")
        category = "edu" if cat_key in ("educational", "science") else "fun"
        name = info.get("name", handle)
        video_store.add_channel(
            body.child_id, name, "allowed",
            handle=info.get("handle"),
            category=category,
        )
        imported.append(handle)

    return {"imported": imported, "count": len(imported), "child_id": body.child_id}


# ── Watch Heartbeat ─────────────────────────────────────────────────

@router.post("/watch-heartbeat")
@limiter.limit("10/minute")
async def watch_heartbeat(request: Request, body: HeartbeatBody):
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

    # Free day pass — unlimited
    free_day = video_store.get_child_setting(child_id, "free_day_date", "")
    is_free_day = free_day == today

    if is_free_day:
        remaining_min = float(limit_min)  # show full limit as remaining
    else:
        remaining_min = max(0.0, limit_min - used_min)

    return TimeStatusResponse(
        limit_min=limit_min,
        used_min=round(used_min, 1),
        remaining_min=round(remaining_min, 1),
        remaining_sec=-1 if is_free_day else int(remaining_min * 60),
        exceeded=False if is_free_day else remaining_min <= 0,
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


# ── HLS Session Management ─────────────────────────────────────────

async def _start_hls_session(
    video_id: str, pair: tuple[str, str], duration: float = 0
) -> str:
    """Start ffmpeg HLS mux in background and wait for the first segment.

    Returns the session_id that can be used to serve HLS files.
    """
    video_url, audio_url = pair
    session_id = uuid.uuid4().hex[:12]
    session_dir = os.path.join(tempfile.gettempdir(), f"brg_hls_{session_id}")
    os.makedirs(session_dir, exist_ok=True)

    playlist_path = os.path.join(session_dir, "index.m3u8")
    segment_pattern = os.path.join(session_dir, "seg_%03d.ts")

    cmd = [
        _FFMPEG_PATH,
        "-nostdin", "-loglevel", "warning",
        "-reconnect", "1", "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-i", video_url,
        "-reconnect", "1", "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-i", audio_url,
        "-c", "copy",
        "-f", "hls",
        "-hls_time", str(_HLS_SEGMENT_SECONDS),
        "-hls_playlist_type", "event",
        "-hls_segment_type", "mpegts",
        "-hls_segment_filename", segment_pattern,
        "-hls_flags", "temp_file+independent_segments",
        playlist_path,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    _hls_sessions[session_id] = {
        "dir": session_dir,
        "process": process,
        "video_id": video_id,
        "duration": duration,
        "pair": pair,
        "created_at": time.time(),
        "ffmpeg_start_seg": 0,
    }

    logger.info("HLS session %s started for %s (pid %d)", session_id, video_id, process.pid)

    # Wait for the first segment to be written (temp_file ensures it's complete)
    first_segment = os.path.join(session_dir, "seg_000.ts")
    for _ in range(60):  # 30 seconds max
        if os.path.exists(first_segment) and os.path.getsize(first_segment) > 0:
            break
        if process.returncode is not None:
            stderr = await process.stderr.read()
            _cleanup_hls_session(session_id)
            logger.error("ffmpeg HLS failed for %s: %s", video_id, stderr.decode(errors="replace")[:500])
            raise HTTPException(status_code=502, detail="Failed to start HLS stream")
        await asyncio.sleep(0.5)
    else:
        process.kill()
        await process.wait()
        _cleanup_hls_session(session_id)
        raise HTTPException(status_code=504, detail="HLS segment generation timed out")

    return session_id


def _generate_vod_playlist(total_duration: float, segment_time: float = _HLS_SEGMENT_SECONDS) -> str:
    """Generate a synthetic VOD playlist with known total duration.

    Lists all expected segments upfront with #EXT-X-ENDLIST so AVPlayer
    shows the full duration scrubber and enables seeking from the start.
    Segments are served by the HLS endpoint as ffmpeg creates them.
    """
    n_segments = max(1, math.ceil(total_duration / segment_time))
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{int(math.ceil(segment_time))}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        "#EXT-X-INDEPENDENT-SEGMENTS",
    ]
    remaining = total_duration
    for i in range(n_segments):
        dur = min(segment_time, remaining)
        if dur < 0.1:
            break
        lines.append(f"#EXTINF:{dur:.3f},")
        lines.append(f"seg_{i:03d}.ts")
        remaining -= segment_time
    lines.append("#EXT-X-ENDLIST")
    lines.append("")
    return "\n".join(lines)


def _highest_segment_on_disk(session_dir: str) -> int:
    """Find the highest segment number that exists on disk."""
    highest = -1
    for f in os.listdir(session_dir):
        if f.startswith("seg_") and f.endswith(".ts"):
            try:
                highest = max(highest, int(f[4:-3]))
            except ValueError:
                pass
    return highest


async def _restart_ffmpeg_at(session_id: str, target_seg: int):
    """Kill current ffmpeg and restart seeking to the target segment.

    Used when the user seeks far ahead of where ffmpeg has processed.
    ffmpeg uses input-level -ss for fast keyframe-based seeking.
    """
    session = _hls_sessions.get(session_id)
    if not session:
        return

    proc = session.get("process")
    if proc and proc.returncode is None:
        proc.kill()
        await proc.wait()

    pair = session.get("pair")
    if not pair:
        return

    video_url, audio_url = pair
    session_dir = session["dir"]
    playlist_path = os.path.join(session_dir, "index.m3u8")
    segment_pattern = os.path.join(session_dir, "seg_%03d.ts")
    target_time = str(target_seg * _HLS_SEGMENT_SECONDS)

    cmd = [
        _FFMPEG_PATH,
        "-nostdin", "-loglevel", "warning",
        "-ss", target_time,
        "-reconnect", "1", "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-i", video_url,
        "-ss", target_time,
        "-reconnect", "1", "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-i", audio_url,
        "-c", "copy",
        "-f", "hls",
        "-hls_time", str(_HLS_SEGMENT_SECONDS),
        "-hls_playlist_type", "event",
        "-hls_segment_type", "mpegts",
        "-start_number", str(target_seg),
        "-hls_segment_filename", segment_pattern,
        "-hls_flags", "temp_file+independent_segments",
        playlist_path,
    ]

    new_process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    session["process"] = new_process
    session["ffmpeg_start_seg"] = target_seg
    logger.info(
        "Restarted ffmpeg for session %s at seg %d (%.0fs)",
        session_id, target_seg, float(target_time),
    )


def _cleanup_hls_session(session_id: str):
    """Remove a session's temp directory and kill its ffmpeg process."""
    session = _hls_sessions.pop(session_id, None)
    if not session:
        return
    proc = session.get("process")
    if proc and proc.returncode is None:
        proc.kill()
    shutil.rmtree(session["dir"], ignore_errors=True)
    logger.info("Cleaned up HLS session %s", session_id)


def _cleanup_expired_sessions():
    """Remove sessions older than _HLS_SESSION_MAX_AGE."""
    now = time.time()
    expired = [
        sid for sid, s in _hls_sessions.items()
        if now - s["created_at"] > _HLS_SESSION_MAX_AGE
    ]
    for sid in expired:
        _cleanup_hls_session(sid)


# ── Helpers ─────────────────────────────────────────────────────────

def _get_remaining_seconds(child_id: int) -> int:
    """Calculate remaining watch seconds for a child today. Returns -1 if no limit."""
    tz = config.watch_limits.timezone
    today = get_today_str(tz)

    # Free day pass — unlimited
    free_day = video_store.get_child_setting(child_id, "free_day_date", "")
    if free_day == today:
        return -1

    limit_str = video_store.get_child_setting(child_id, "daily_limit_minutes", "")
    if not limit_str:
        limit_min = config.watch_limits.daily_limit_minutes
    else:
        limit_min = int(limit_str)

    if limit_min == 0:
        return -1

    bounds = get_day_utc_bounds(today, tz)
    used_min = video_store.get_daily_watch_minutes(child_id, today, utc_bounds=bounds)
    remaining = max(0.0, limit_min - used_min)
    return int(remaining * 60)
