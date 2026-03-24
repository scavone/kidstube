# Test Plan: Issue #31 — Viewing Session Windows with Cooldown Periods

**Date:** 2026-03-24
**Status:** Phase 1 (pre-implementation)
**Reviewer:** qa-analyst

---

## Overview

Issue #31 adds session-based viewing windows with cooldowns between sessions. A child can watch for N minutes (a "session"), then must wait M minutes (the "cooldown") before the next session begins. Sessions are counted per day and capped at a configurable maximum.

This extends the existing daily time-limit and schedule systems without replacing them.

---

## Architecture Assumptions

Based on the existing codebase patterns:

- Session config stored in `child_settings` table via `set_child_setting` (keys: `session_duration_minutes`, `cooldown_minutes`, `max_sessions_per_day`)
- Session status computed from `watch_log` rows (accumulated playback seconds within a rolling window)
- New endpoint(s) added to `api/routes.py` — likely `GET /api/session-status`
- New Pydantic response model in `api/models.py`
- New Swift model in `tvos/Sources/Models/`
- New `APIClient` method in `tvos/Sources/Services/APIClient.swift`
- New tvOS view: CooldownView (or integrated into existing TimesUp/WindDown screen)
- Backward compat: if no session config exists, behavior is unchanged

---

## Test Areas

### 1. Backend — Session Config CRUD

#### 1.1 Telegram Bot Commands
- [ ] `/sessions <child> <duration_min> <cooldown_min> [max_sessions]` — sets all three settings
- [ ] `/sessions <child> off` — removes session config, restores unlimited behavior
- [ ] `/sessions <child>` (no args) — shows current session config
- [ ] Invalid args (negative duration, non-numeric input, missing child) return clear error messages
- [ ] Unknown child name returns helpful error
- [ ] Partial config (only duration set, no cooldown) is handled gracefully

#### 1.2 VideoStore / child_settings persistence
- [ ] `set_child_setting(child_id, "session_duration_minutes", "30")` persists correctly
- [ ] `set_child_setting(child_id, "cooldown_minutes", "10")` persists correctly
- [ ] `set_child_setting(child_id, "max_sessions_per_day", "3")` persists correctly
- [ ] `get_child_setting` retrieves correct values after set
- [ ] Settings survive VideoStore close/reopen (SQLite persistence)
- [ ] Missing settings return sensible defaults (no session limit = unlimited)

---

### 2. Backend — Session Status Computation

#### 2.1 Normal flow — session in progress
- [ ] Child has watched 15 of 30 allowed session minutes → `state: "in_session"`, `session_remaining_sec: 900`
- [ ] Watch time accumulated from `watch_log` (not wall clock) so pausing doesn't drain cooldown
- [ ] `used_session_sec` reflects only current session's watch time
- [ ] `sessions_completed` count is accurate

#### 2.2 Cooldown active
- [ ] After completing a 30-min session, cooldown begins immediately
- [ ] `state: "cooldown"` with `cooldown_remaining_sec` counting down from server-computed start
- [ ] Cooldown is wall-clock based (not watch-time based) — player is blocked even with 0 watch time
- [ ] `cooldown_remaining_sec` = `cooldown_minutes * 60 - elapsed_wall_seconds_since_session_end`

#### 2.3 Edge cases — no config (backward compat)
- [ ] If `session_duration_minutes` is not set → endpoint returns `state: "no_sessions"` or equivalent indicating no session limit
- [ ] Existing endpoints (`/api/time-status`, `/api/heartbeat`) unchanged in behavior
- [ ] App with no session config continues working exactly as before

#### 2.4 Edge case — no watch time yet today
- [ ] First request of the day → `state: "in_session"`, `sessions_completed: 0`, full session remaining
- [ ] `used_session_sec: 0`

#### 2.5 Edge case — max sessions reached
- [ ] All 3 sessions consumed (e.g., 3×30-min sessions) → `state: "sessions_exhausted"`
- [ ] `sessions_remaining: 0`
- [ ] `cooldown_remaining_sec: 0` (not in cooldown — just done for the day)
- [ ] Distinguishable from active cooldown state (different state value)

#### 2.6 Edge case — cooldown spanning midnight
- [ ] Session ends at 11:55 PM, 10-minute cooldown spans into next day (00:05 AM)
- [ ] Server should NOT carry cooldown state into next day — midnight resets sessions
- [ ] If cooldown end time > midnight, it is truncated to midnight (child gets full next-day sessions)

#### 2.7 Edge case — mid-day config change
- [ ] Parent changes session duration from 30→20 min while session is already in progress
- [ ] If already used 25 min, new 20-min limit means session is immediately over → `state: "cooldown"`
- [ ] Session count for the day uses the new config going forward
- [ ] Cooldown duration change takes effect on next cooldown start

#### 2.8 Edge case — daily limit reached before session limit
- [ ] Child has 3 allowed sessions but daily limit of 60 min
- [ ] After 60 min total watch time, `time-status` endpoint reports `exceeded: true`
- [ ] Session-status should NOT independently unlock the child — both limits must be satisfied
- [ ] The app must check both endpoints and show the most restrictive constraint

#### 2.9 Session counting logic
- [ ] Sessions are counted per UTC day (consistent with existing `get_daily_watch_minutes`)
- [ ] Session boundaries determined by gaps in watch_log? Or by explicit session records?
- [ ] Concurrent watch from two devices doesn't double-count (threading lock prevents race)

---

### 3. Backend — API Endpoint

#### 3.1 `GET /api/session-status?child_id=N`
- [ ] Returns 200 with correct schema when sessions are configured
- [ ] Returns 200 with `state: "no_sessions"` (or no-op response) when not configured
- [ ] Returns 404 if `child_id` does not exist
- [ ] Requires Bearer auth (returns 401 without it)
- [ ] Response fields (proposed contract to verify against implementation):
  ```json
  {
    "state": "in_session|cooldown|sessions_exhausted|no_sessions",
    "session_duration_min": 30,
    "cooldown_min": 10,
    "max_sessions": 3,
    "sessions_completed": 1,
    "sessions_remaining": 2,
    "session_remaining_sec": 900,
    "cooldown_remaining_sec": 0,
    "used_session_sec": 900
  }
  ```
- [ ] All integer/numeric fields — no float ambiguity
- [ ] `session_remaining_sec` is 0 when not in session
- [ ] `cooldown_remaining_sec` is 0 when not in cooldown

#### 3.2 Integration with existing heartbeat endpoint
- [ ] `POST /api/heartbeat` still returns `remaining` (daily seconds) as before
- [ ] Heartbeat does NOT need to return session data — session-status is polled separately
- [ ] Heartbeat increments `watch_log` which session-status reads

---

### 4. Frontend — Cooldown Screen

#### 4.1 Visual states
- [ ] **In-session:** No cooldown UI shown; normal playback allowed
- [ ] **Cooldown active:** Full-screen "cooldown" overlay shown, player blocked
- [ ] **Sessions exhausted:** "No more sessions today" screen shown (distinct from cooldown)
- [ ] **No session config:** App behaves exactly as before (no cooldown screen, no regressions)

#### 4.2 Countdown timer accuracy
- [ ] Countdown timer decrements every second using a local Timer
- [ ] Timer is initialized from `cooldown_remaining_sec` returned by server (server-authoritative)
- [ ] Timer does NOT drift: it decrements by wall-clock seconds, not by polling interval
- [ ] When timer reaches 0, app re-polls `/api/session-status` to confirm cooldown ended server-side
- [ ] App does NOT automatically unlock based solely on client timer reaching 0 — server confirmation required

#### 4.3 Auto-unlock on cooldown end
- [ ] After timer hits 0, app polls session-status and gets `state: "in_session"` → navigates back to home/player
- [ ] If server still returns `state: "cooldown"` (e.g., clock skew), timer resets to new `cooldown_remaining_sec`
- [ ] Poll interval during cooldown: reasonable (e.g., every 5 seconds near end, every 30 during cooldown)

#### 4.4 Navigation lock during cooldown
- [ ] Back button on cooldown screen is disabled or redirects to same screen
- [ ] Cannot navigate to player while cooldown is active
- [ ] Deep link or direct navigation to video is blocked during cooldown
- [ ] PIN-protected profile switch: cooldown is per-profile, switching profiles should bypass (if allowed by parent config)

#### 4.5 App backgrounded during cooldown
- [ ] App backgrounded at T=0 (start of cooldown), foregrounded at T=5min (cooldown=10min)
- [ ] On foreground, app re-polls session-status → receives updated `cooldown_remaining_sec: 300` → timer resumes correctly
- [ ] App does NOT reset timer to the original full cooldown value on foreground
- [ ] If app foregrounded after cooldown has already expired, it shows unlocked state

#### 4.6 Integration with wind-down overlay (Issue #30)
- [ ] If session ends because session limit reached (not daily limit), wind-down overlay shows cooldown screen (not "times up")
- [ ] If daily limit reached during session, "times up" takes precedence over cooldown
- [ ] Visual distinction between "cooldown" and "times up" states is clear to child

#### 4.7 Sessions exhausted vs cooldown states
- [ ] CooldownView (or equivalent) has two distinct modes:
  - Mode A: "Take a break! Back in Xm Ys" (countdown timer visible)
  - Mode B: "No more watching today" (no timer, come back tomorrow)
- [ ] Mode A shown when `state == "cooldown"`
- [ ] Mode B shown when `state == "sessions_exhausted"`
- [ ] Neither mode allows playback

---

### 5. Integration — API Contract Alignment

#### 5.1 Field names and types
- [ ] Swift `CodingKeys` use snake_case matching Python field names exactly
- [ ] `session_remaining_sec: Int` in Swift ↔ `session_remaining_sec: int` in Python
- [ ] `cooldown_remaining_sec: Int` in Swift ↔ `cooldown_remaining_sec: int` in Python
- [ ] `state: String` in Swift (not an enum) for forward compatibility
- [ ] Nullable fields (if any) use `Optional` in Swift and `Optional[T]` in Python

#### 5.2 Endpoint path and method
- [ ] Swift `APIClient` calls `GET /api/session-status?child_id=N` — path must match route exactly
- [ ] Auth header included (Bearer token)
- [ ] Query param `child_id` type: `Int` in Swift, `int` in Python

#### 5.3 Backward compatibility when sessions not configured
- [ ] Server returns a valid response (not 404, not 500) when sessions not configured
- [ ] Swift model decodes the "no sessions" response without crashing
- [ ] App correctly treats `state == "no_sessions"` as "no restrictions from sessions"
- [ ] Existing tests for `time-status`, `schedule-status`, `heartbeat` still pass unmodified

#### 5.4 Telegram bot command integration
- [ ] Bot command stores settings that the API endpoint reads from the same `child_settings` keys
- [ ] Key name consistency: bot writes `session_duration_minutes`, API reads `session_duration_minutes` (exact match)

---

## Test Implementation Plan

### Server Tests (pytest)
File: `server/tests/test_session_cooldowns.py`

```
TestSessionConfig
  - test_set_get_session_settings
  - test_session_settings_persist
  - test_missing_session_settings_default

TestSessionStatusEndpoint
  - test_no_session_config_returns_no_sessions_state
  - test_child_not_found_returns_404
  - test_missing_auth_returns_401
  - test_first_request_of_day_full_session_remaining
  - test_in_progress_session_reduces_remaining
  - test_completed_session_triggers_cooldown
  - test_cooldown_decrements_with_wall_clock
  - test_max_sessions_exhausted_state
  - test_daily_limit_reached_before_session_limit
  - test_cooldown_spanning_midnight_resets
  - test_mid_day_config_change_applies

TestSessionTelegramBot (in test_telegram_bot.py or new file)
  - test_sessions_command_sets_config
  - test_sessions_off_removes_config
  - test_sessions_command_shows_current_config
  - test_sessions_command_invalid_args_error
  - test_sessions_command_unknown_child_error
```

### tvOS Tests (Swift Testing)
File: `tvos/Tests/SessionStatusTests.swift`

```swift
@Suite("SessionStatus")
  - test_decode_in_session_state
  - test_decode_cooldown_state
  - test_decode_sessions_exhausted_state
  - test_decode_no_sessions_state
  - test_session_remaining_sec_zero_when_not_in_session
  - test_cooldown_remaining_sec_zero_when_not_in_cooldown
  - test_is_in_cooldown_computed_property
  - test_is_sessions_exhausted_computed_property
  - test_has_session_limit_computed_property
  - test_decode_missing_optional_fields_does_not_crash
  - test_cooldown_remaining_formatted_string

@Suite("APIClient+SessionStatus")
  - test_get_session_status_in_session
  - test_get_session_status_cooldown
  - test_get_session_status_no_sessions
  - test_get_session_status_404_throws
```

---

## Edge Case Priority Matrix

| Edge Case | Risk Level | Why |
|-----------|-----------|-----|
| Cooldown spanning midnight | HIGH | Could block child at start of next day |
| Daily limit + session limit interaction | HIGH | Could show wrong screen, or unlock too early |
| App foregrounded after cooldown expires | HIGH | Timer state could be stale → wrong UX |
| Mid-day config change during session | MEDIUM | Parent changing settings live |
| Sessions exhausted vs cooldown display | MEDIUM | Different messages needed, easy to mix up |
| No session config backward compat | HIGH | Must not break existing installs |
| Server clock skew on timer end | LOW | Timer over-counts by a few seconds max |

---

## Files to Review in Phase 2

### Backend (expected new/modified)
- `server/data/video_store.py` — any new session-related methods
- `server/api/routes.py` — new `/api/session-status` endpoint
- `server/api/models.py` — new `SessionStatusResponse` model
- `server/bot/telegram_bot.py` — new `/sessions` command handler
- `server/tests/test_session_cooldowns.py` (new)

### Frontend (expected new/modified)
- `tvos/Sources/Models/TimeStatus.swift` or new `SessionStatus.swift`
- `tvos/Sources/Services/APIClient.swift` — `getSessionStatus(childId:)`
- `tvos/Sources/Views/` — new CooldownView or modified TimesUp/WindDown
- `tvos/Tests/SessionStatusTests.swift` (new)

---

## Baseline Test Run

Executed 2026-03-24 before any implementation:

- **Server (pytest):** 700 passed, 0 failed
- **tvOS (swift test):** 126 passed, 0 failed

Phase 2 will re-run to confirm no regressions introduced by the implementation.
