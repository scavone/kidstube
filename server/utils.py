"""Shared utilities — time parsing, formatting, and schedule checking."""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Matches: 800, 0800, 8:00, 800am, 8:00am, 800pm, 8:00PM, 2000, 20:00
_TIME_RE = re.compile(
    r"^(\d{1,2}):?(\d{2})\s*(am|pm)?$",
    re.IGNORECASE,
)


def get_today_str(tz_name: str = "") -> str:
    """Get today's date as YYYY-MM-DD in the given timezone.

    Falls back to UTC if tz_name is empty or invalid.
    """
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(tz_name)
            return datetime.now(tz).strftime("%Y-%m-%d")
        except Exception:
            logger.warning("Invalid timezone %r, falling back to UTC", tz_name)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_day_utc_bounds(date_str: str, tz_name: str = "") -> tuple[str, str]:
    """Convert a local date (YYYY-MM-DD) to UTC start/end timestamps.

    Returns (start_utc, end_utc) as ISO strings for use in SQL queries
    against UTC-stored watched_at timestamps.
    """
    local_date = datetime.strptime(date_str, "%Y-%m-%d")
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(tz_name)
            start_local = local_date.replace(tzinfo=tz)
            end_local = (local_date + timedelta(days=1)).replace(tzinfo=tz)
            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)
            return (
                start_utc.strftime("%Y-%m-%d %H:%M:%S"),
                end_utc.strftime("%Y-%m-%d %H:%M:%S"),
            )
        except Exception:
            logger.warning("Invalid timezone %r for day bounds, using date as-is", tz_name)
    next_day = (local_date + timedelta(days=1)).strftime("%Y-%m-%d")
    return (date_str, next_day)


def parse_time_input(raw: str) -> str | None:
    """Parse flexible time input into 24-hour "HH:MM" format.

    Accepts: 800, 0800, 8:00, 800am, 8:00am, 800pm, 8:00PM, 2000, 20:00
    Returns normalized "HH:MM" string or None if invalid.
    """
    raw = raw.strip()
    m = _TIME_RE.match(raw)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2))
    meridiem = (m.group(3) or "").lower()

    if meridiem == "am":
        if hour == 12:
            hour = 0
        elif hour > 12:
            return None
    elif meridiem == "pm":
        if hour == 12:
            pass
        elif hour > 12:
            return None
        else:
            hour += 12
    else:
        if hour > 23:
            return None

    if minute > 59:
        return None

    return f"{hour:02d}:{minute:02d}"


def format_time_12h(hhmm: str) -> str:
    """Convert "HH:MM" to human-readable 12-hour format.

    "08:00" -> "8:00 AM", "20:00" -> "8:00 PM", "00:00" -> "12:00 AM"
    """
    try:
        h, m = map(int, hhmm.split(":"))
    except (ValueError, AttributeError):
        return hhmm
    if h == 0:
        return f"12:{m:02d} AM"
    elif h < 12:
        return f"{h}:{m:02d} AM"
    elif h == 12:
        return f"12:{m:02d} PM"
    else:
        return f"{h - 12}:{m:02d} PM"


def format_duration(seconds: int | None) -> str:
    """Format seconds into human-readable duration.

    120 -> "2:00", 3661 -> "1:01:01", None -> "?"
    """
    if seconds is None or seconds < 0:
        return "?"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def is_within_schedule(
    start_str: str, end_str: str, tz_name: str = ""
) -> tuple[bool, str]:
    """Check if current time falls within the scheduled access window.

    Returns (allowed, unlock_time_display).
    """
    if not start_str and not end_str:
        return (True, "")

    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            now = datetime.now(ZoneInfo(tz_name))
        except Exception:
            now = datetime.now(timezone.utc)
    else:
        now = datetime.now(timezone.utc)

    now_minutes = now.hour * 60 + now.minute

    if start_str and not end_str:
        try:
            sh, sm = map(int, start_str.split(":"))
        except (ValueError, AttributeError):
            return (True, "")
        allowed = now_minutes >= sh * 60 + sm
        unlock_time = format_time_12h(start_str) if not allowed else ""
        return (allowed, unlock_time)

    if end_str and not start_str:
        try:
            eh, em = map(int, end_str.split(":"))
        except (ValueError, AttributeError):
            return (True, "")
        allowed = now_minutes < eh * 60 + em
        unlock_time = "tomorrow" if not allowed else ""
        return (allowed, unlock_time)

    # Both set
    try:
        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))
    except (ValueError, AttributeError):
        return (True, "")

    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    if start_minutes <= end_minutes:
        allowed = start_minutes <= now_minutes < end_minutes
    else:
        allowed = now_minutes >= start_minutes or now_minutes < end_minutes

    unlock_time = format_time_12h(start_str) if not allowed else ""
    return (allowed, unlock_time)


# ── Per-Day Schedule Helpers ────────────────────────────────────────

# Day names used as keys in child_settings (schedule:monday, etc.)
_DAY_NAMES = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]


def resolve_day_schedule(
    settings: dict[str, str], tz_name: str = ""
) -> tuple[str, str]:
    """Resolve the start/end times for today from per-day or default schedule.

    Checks for ``schedule:<dayname>`` keys first (e.g. ``schedule:monday``),
    then falls back to ``schedule:default``, then to the legacy
    ``schedule_start``/``schedule_end`` keys.

    Per-day values are JSON: ``{"start": "15:00", "end": "19:00"}``.

    Returns (start_hhmm, end_hhmm) — both empty if no schedule is configured.
    """
    import json

    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo(tz_name))
        except Exception:
            now = datetime.now(timezone.utc)
    else:
        now = datetime.now(timezone.utc)

    day_name = _DAY_NAMES[now.weekday()]

    # 1. Try schedule:<dayname>
    day_key = f"schedule:{day_name}"
    if day_key in settings and settings[day_key]:
        try:
            data = json.loads(settings[day_key])
            return (data.get("start", ""), data.get("end", ""))
        except (json.JSONDecodeError, AttributeError):
            pass

    # 2. Try schedule:default
    default_key = "schedule:default"
    if default_key in settings and settings[default_key]:
        try:
            data = json.loads(settings[default_key])
            return (data.get("start", ""), data.get("end", ""))
        except (json.JSONDecodeError, AttributeError):
            pass

    # 3. Fall back to legacy schedule_start / schedule_end
    return (settings.get("schedule_start", ""), settings.get("schedule_end", ""))


def minutes_until_schedule_end(end_str: str, tz_name: str = "") -> int:
    """Calculate minutes remaining until the schedule window ends.

    Returns -1 if no end time is set.  Handles cross-midnight correctly
    (wraps around by adding 24h).
    """
    if not end_str:
        return -1

    try:
        eh, em = map(int, end_str.split(":"))
    except (ValueError, AttributeError):
        return -1

    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo(tz_name))
        except Exception:
            now = datetime.now(timezone.utc)
    else:
        now = datetime.now(timezone.utc)

    now_minutes = now.hour * 60 + now.minute
    end_minutes = eh * 60 + em

    diff = end_minutes - now_minutes
    if diff < 0:
        diff += 24 * 60  # crosses midnight

    return diff


# ── Session Windowing ────────────────────────────────────────────────

def compute_session_state(
    session_config: dict,
    watch_entries: list,
    now: datetime,
) -> dict:
    """Compute current session state from watch_log entries.

    Args:
        session_config: dict with session_duration_minutes, cooldown_duration_minutes,
                        max_sessions_per_day (None = uncapped)
        watch_entries: list of (duration_seconds, watched_at_utc_str) sorted ASC
        now: current UTC datetime (tz-aware)

    Returns a dict matching SessionStatusResponse fields (sessions_enabled=True).
    """
    session_dur_sec = session_config["session_duration_minutes"] * 60
    cooldown_dur_sec = session_config["cooldown_duration_minutes"] * 60
    max_sessions: Optional[int] = session_config.get("max_sessions_per_day")

    sessions_completed = 0
    accumulated = 0  # seconds accumulated in current in-progress session
    in_cooldown = False
    cooldown_end: Optional[datetime] = None

    for duration_sec, watched_at_str in watch_entries:
        try:
            watched_at = datetime.fromisoformat(watched_at_str)
            if watched_at.tzinfo is None:
                watched_at = watched_at.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            continue

        if in_cooldown:
            if cooldown_end and watched_at >= cooldown_end:
                # Cooldown elapsed — start fresh session
                in_cooldown = False
                cooldown_end = None
                accumulated = 0
            else:
                # Still in cooldown — skip this heartbeat
                continue

        accumulated += duration_sec

        if accumulated >= session_dur_sec:
            sessions_completed += 1
            accumulated = 0

            if max_sessions is not None and sessions_completed >= max_sessions:
                # Sessions exhausted — no more cooldown needed
                in_cooldown = False
                break

            cooldown_end = watched_at + timedelta(seconds=cooldown_dur_sec)
            in_cooldown = True

    # Re-check cooldown against current time
    if in_cooldown and cooldown_end and now >= cooldown_end:
        in_cooldown = False
        cooldown_end = None

    sessions_exhausted = (
        max_sessions is not None and sessions_completed >= max_sessions
    )
    current_session = sessions_completed + 1

    if sessions_exhausted:
        session_time_remaining_sec = 0
        cooldown_remaining_sec = 0
        next_session_at = None
    elif in_cooldown and cooldown_end:
        session_time_remaining_sec = 0
        cooldown_remaining_sec = max(0, int((cooldown_end - now).total_seconds()))
        next_session_at = cooldown_end.isoformat()
    else:
        session_time_remaining_sec = max(0, session_dur_sec - accumulated)
        cooldown_remaining_sec = 0
        next_session_at = None

    return {
        "sessions_enabled": True,
        "current_session": current_session,
        "max_sessions": max_sessions,
        "session_duration_minutes": session_config["session_duration_minutes"],
        "cooldown_duration_minutes": session_config["cooldown_duration_minutes"],
        "session_time_remaining_seconds": session_time_remaining_sec,
        "in_cooldown": in_cooldown,
        "cooldown_remaining_seconds": cooldown_remaining_sec,
        "next_session_at": next_session_at,
        "sessions_exhausted": sessions_exhausted,
    }
