# QA Report: Issue #6 — Per-Child Category Time Limits

**Date:** 2026-03-25
**Reviewer:** qa-analyst
**Status:** PASS WITH FINDINGS

---

## Test Execution Results

| Suite | Before | After | Delta |
|-------|--------|-------|-------|
| Server (`pytest`) | 723 | 755 | +32 new tests |
| tvOS (`swift test`) | 133 | 133 | 0 (no new Swift tests) |
| tvOS build (`xcodebuild`) | ✅ | ✅ | — |
| File conflicts | — | ✅ None | — |

All tests pass. Build succeeds. No file conflicts between devs.

---

## API Contract Alignment

| Check | Result | Notes |
|-------|--------|-------|
| Endpoint URL | ✅ PASS | Both sides use `GET /api/category-time-status` |
| `limit_minutes` / `limitMinutes` | ✅ PASS | CodingKey correct |
| `used_minutes` / `usedMinutes` | ✅ PASS | CodingKey correct |
| `remaining_minutes` / `remainingMinutes` | ✅ PASS | CodingKey correct |
| `remaining_seconds` / `remainingSeconds` | ✅ PASS | CodingKey correct |
| `bonus_minutes` / `bonusMinutes` | ✅ PASS | CodingKey correct |
| `exhausted` / `exhausted` | ✅ PASS | No mapping needed |
| `uncapped_categories` / `uncappedCategories` | ✅ PASS | CodingKey correct |
| Missing `categories` field → graceful decode | ✅ PASS | Swift defaults empty dict |
| `HeartbeatResponse.remaining = 0` on category exhaustion | ✅ PASS | Server returns 0 when category exhausted |

---

## Feature Area Checks

### Migration
- [x] `category TEXT NOT NULL DEFAULT 'fun'` column added to `watch_log` via `_migrate()`
- [x] Migration is idempotent (checks `PRAGMA table_info` before `ALTER TABLE`)
- [x] Existing rows automatically backfilled with `'fun'` via `DEFAULT 'fun'`
- [x] `TestBackwardCompatibility::test_watch_log_without_category_column_still_works` confirms this end-to-end

### Category Limit CRUD
- [x] `set_category_limit` / `get_category_limits` / `clear_category_limit` all work correctly
- [x] Multiple categories settable independently per child
- [x] Updating a limit replaces the old value (upsert semantics)
- [x] Clearing a nonexistent limit is a no-op

### Category Watch Minutes
- [x] `get_daily_category_watch_minutes` filters by category correctly
- [x] Timezone-bound UTC filtering applied
- [x] Falls back to `'fun'` for unknown videos (no video record → `'fun'`)
- [x] Category priority: `video.category` → `channel.category` → `'fun'`

### Bonus Time
- [x] Per-category bonus (`add_category_bonus`) accumulates for same date+category
- [x] Bonus is date-scoped (previous day's bonus returns 0)
- [x] Bonus is category-scoped (fun bonus doesn't affect edu)
- [x] Bonus adds to effective limit in `category_time_status` endpoint: `remaining = limit + bonus - used`

### Heartbeat Most-Restrictive Logic
- [x] Category check only runs when global limit hasn't already expired (`if remaining != 0`)
- [x] When `remaining == -1` (no global limit), category check still runs
- [x] Category exhaustion sets `remaining = 0` in heartbeat response
- [x] `get_video_effective_category` used correctly to determine video's category at heartbeat time

### Pre-launch Category Block
- [x] `ContentView.playVideo()` checks `categoryTimeStatus` before opening player
- [x] Exhausted category → `overlayScreen = .categoryTimesUp` shown before stream request
- [x] Uncapped categories not blocked (correct `uncappedCategories` check)
- [x] Falls back to `video.effectiveCategory ?? video.category`

### Overlay Correctness
- [x] `CategoryTimesUpView` is distinct from global `TimesUpView`
- [x] `WindDownReason` enum: `.dailyLimit` vs `.categoryLimit(label:)` differentiated
- [x] Wind-down overlay title changes correctly: "Time's Up!" vs "Entertainment Time Up!"
- [x] `CategoryTimesUpView` text: "No more [Category] time today!"

### Sidebar
- [x] `categoryTimeStatus` passed to `SidebarView`
- [x] Per-category time remaining shown as subtitle ("42 min left", "1h 5m left")
- [x] Exhausted categories dimmed via `isExhausted`
- [x] Uncapped categories not dimmed

### Backward Compatibility
- [x] `GET /api/time-status` returns `category_status: null` when no limits configured
- [x] All existing `TimeStatusResponse` fields unchanged (`limit_min`, `used_min`, etc.)
- [x] No regressions in existing 723 server tests

---

## Issues Found

### 🔴 BUG (Medium) — Wrong overlay shown on mid-video category exhaustion

**File:** `tvos/Sources/Views/Player/PlayerView.swift:101-115`

**Root cause:** Two independent 30-second tasks compete — the heartbeat and the category poller. When a category limit is exhausted mid-video:

1. Heartbeat fires first (it starts before the category poller), server returns `remaining = 0`
2. `HeartbeatService.isTimeExceeded = true` → `windDownReason = .dailyLimit`, `showWindDown = true`
3. Category poller fires next and hits `guard !self.showWindDown` → **skips** because already showing wind-down
4. `isCategoryTimeExceeded` never gets set with `.categoryLimit` reason
5. **User sees "Time's Up!" (global daily overlay) instead of "Entertainment Time Up!" (category overlay)**

This is the common case, not a race — the heartbeat consistently starts ~first.

**Reproduction:** Set only a category limit (no global daily limit). Watch a video in that category until the category is exhausted. The global "Time's Up!" screen will appear instead of the category-specific one.

**Suggested fix:** In the heartbeat `onChange` handler (line 101), before setting `windDownReason = .dailyLimit`, check whether the category is exhausted by consulting `viewModel.videoCategory` and the known category limit. If the category is exhausted but the global limit still has time, use `.categoryLimit` reason instead. Alternatively, the server could return a structured response distinguishing the cause of `remaining = 0`.

---

### 🟡 FINDING (Low) — Unused variable in `PlayerView.swift`

**File:** `tvos/Sources/Views/Player/PlayerView.swift:109`

```swift
if exceeded, let category = videoCategory {  // `category` is declared but never used
    windDownReason = .categoryLimit(label: categoryLabel)
```

`category` is bound by `let category = videoCategory` but the body uses `categoryLabel` (a computed property that also derives from `videoCategory`). This produces a Swift compiler warning. Since `categoryLabel` handles the nil case, the `let category = videoCategory` guard can be simplified to `if exceeded {` or `if exceeded, videoCategory != nil {`.

---

### 🟡 FINDING (Low) — No wind-down advance warning for category limits

The heartbeat response carries the GLOBAL remaining seconds, not the smaller of (global, category). When a category has 45 seconds left but global has 10 minutes remaining, the player shows the global countdown bar at ~10 minutes and gives no "2-minute warning" specific to the category. The child's video stops abruptly (within 30s of exhaustion via the category poller) without the usual wind-down UX.

This is a UX degradation relative to the global limit experience. The existing wind-down works because the heartbeat's `remainingSeconds` drives the countdown. To fix: either (a) heartbeat returns `min(global, category)` remaining, or (b) the category poller triggers a category-specific wind-down with a countdown when remaining < 120 seconds.

---

### 🟢 INFORMATIONAL — Category label string duplicated

`categoryLabel` switch (`"edu" → "Educational"`, `"fun" → "Entertainment"`) is defined in three places: `ContentView.swift`, `PlayerView.swift`, and `CategoryContentView.swift`. Not a bug, but a future refactor candidate (shared extension on `String` or a global function).

---

## Checklist Against Test Plan

| Test Plan Area | Coverage | Status |
|---|---|---|
| Migration: column added, idempotent | `test_watch_log_without_category_column_still_works` | ✅ |
| Migration: backfill existing rows | Default value test | ✅ |
| Category limit CRUD | `TestCategoryLimitCRUD` (6 tests) | ✅ |
| Category bonus | `TestCategoryBonus` (5 tests) | ✅ |
| Watch minutes by category | `TestCategoryWatchMinutes` (3 tests) | ✅ |
| Heartbeat writes correct category | `TestRecordWatchSeconds` (3 tests) | ✅ |
| `get_video_effective_category` | `TestGetVideoEffectiveCategory` (4 tests) | ✅ |
| `/api/category-time-status` endpoint | `TestCategoryTimeStatusEndpoint` (7 tests) | ✅ |
| Heartbeat most-restrictive-wins | `TestHeartbeatCategoryIntegration` | ❌ NOT WRITTEN |
| Most-restrictive parametrized cases | — | ❌ NOT WRITTEN |
| Free day overrides category limits | — | ❌ NOT WRITTEN |
| Backward compat | `TestBackwardCompatibility` (2 tests) | ✅ |
| Telegram command parsing | manual review only | ⚠️ NO TESTS |

**Gaps in test coverage:**
1. No server test for heartbeat response when category-only exhausted (most-restrictive-wins)
2. No server test for free day overriding category limits
3. No tvOS Swift tests for new category time models or UI logic (0 new tests added)
4. No Telegram bot tests for the new `/time [Child] set/add/clear` subcommands

---

## Recommendation

**Ship with fixes required:**

1. **Must fix before merge:** The mid-video category exhaustion race condition (BUG above) causes the wrong overlay to be shown. This breaks the core user-facing requirement of "show category exhaustion correctly."

2. **Should fix:** Add the missing server-side test for heartbeat most-restrictive-wins and free day override.

3. **Nice to have:** Resolve unused `category` variable warning and consider wind-down advance notice for category limits.
