# Test Plan: Issue #6 — Per-Child Category Time Limits with Remaining Time Display

**Date:** 2026-03-25
**Status:** Phase 1 (pre-implementation)
**Reviewer:** qa-analyst

---

## Overview

Issue #6 adds per-child category time limits so a parent can set separate daily budgets for different content categories (e.g. "fun: 60 min, edu: 90 min"). The tvOS sidebar shows remaining time per category, dims exhausted categories, and blocks playback when a category's limit is hit — independently of the global daily limit.

This extends the existing daily-limit and session-window systems without replacing them.

---

## Architecture Assumptions

Based on existing codebase patterns:

- **Category column** added to `watch_log` so time can be summed per-category
- **Per-category limits** stored in `child_settings` (e.g. key `category_limit_fun_minutes`, `category_limit_edu_minutes`)
- **Per-category bonus time** stored in `child_settings` (e.g. key `category_bonus_fun_minutes`, `category_bonus_fun_date`)
- **Category time API** — new or extended endpoint (likely `GET /api/time-status` extended, or a new `GET /api/category-time-status`)
- **Default category** — videos without an explicit category default to `'fun'`
- **Most-restrictive-wins rule** — playback is blocked when either the global daily limit OR the current category limit is exhausted
- **Free day** — overrides all category limits (child can watch any category freely)
- **Backward compat** — if no category limits are configured, behavior is identical to today

---

## Test Areas

---

### 1. Backend — Database Migration

#### 1.1 `watch_log` category column migration
- [ ] `_migrate()` adds `category TEXT` column to `watch_log` if missing
- [ ] Migration runs on existing databases without error (column not present → added)
- [ ] Migration is idempotent (running twice does not error)
- [ ] Existing rows are backfilled: `category` set to `'fun'` (safe default) OR left NULL with NULL treated as `'fun'` in queries
- [ ] After migration, `PRAGMA table_info(watch_log)` includes `category`

#### 1.2 Heartbeat writes category to `watch_log`
- [ ] `POST /api/heartbeat` writes a `watch_log` row with the correct category derived from the video's channel
- [ ] When a video's channel has no category, row is written with `category = 'fun'` (or configured default)
- [ ] Category value stored matches the `child_channels.category` field for that channel

---

### 2. Backend — Category Limit CRUD

#### 2.1 `child_settings` persistence
- [ ] `set_child_setting(child_id, "category_limit_fun_minutes", "60")` persists correctly
- [ ] `set_child_setting(child_id, "category_limit_edu_minutes", "90")` persists correctly
- [ ] `get_child_setting` retrieves correct values after set
- [ ] Settings survive `VideoStore` close/reopen (SQLite persistence)
- [ ] Missing key returns `""` / sensible default (no limit for that category)
- [ ] Removing a limit (setting to `"0"` or `""`) disables the per-category cap

#### 2.2 Telegram command parsing
- [ ] `/categorylimit <child> <category> <minutes>` — sets limit for given category
- [ ] `/categorylimit <child> <category> off` — removes limit for that category
- [ ] `/categorylimit <child>` (no category) — shows all current category limits
- [ ] Invalid child name returns clear error
- [ ] Invalid minutes (negative, non-numeric) returns clear error
- [ ] Unknown/unsupported category name returns a helpful error or list of valid categories
- [ ] Multiple categories can be set independently for the same child

---

### 3. Backend — Per-Category Time Computation

#### 3.1 Daily usage summing
- [ ] `get_daily_watch_minutes(child_id, today, category='fun')` sums only `watch_log` rows with `category='fun'` for today
- [ ] `get_daily_watch_minutes(child_id, today, category='edu')` sums only `edu` rows
- [ ] `get_daily_watch_minutes(child_id, today)` (no category) sums all rows (existing behavior unchanged)
- [ ] Rows from previous days are excluded
- [ ] Timezone boundary respected (uses child's timezone setting, same as global limit)
- [ ] Child with no watch log entries returns 0 minutes for any category

#### 3.2 Remaining time calculation
- [ ] `remaining = limit - used` computed correctly (not negative — floor at 0)
- [ ] `exceeded = True` when `used >= limit`
- [ ] `remaining_sec` truncated to integer correctly
- [ ] When `limit == 0` (no category limit), category is treated as unrestricted

---

### 4. Backend — Bonus Time Stacking

#### 4.1 Global bonus applies to global limit only
- [ ] Global bonus (`bonus_minutes`) adds to global `limit_min` in `/api/time-status`
- [ ] Global bonus does NOT add to individual category limits (unless spec says otherwise — verify with team lead)

#### 4.2 Per-category bonus time
- [ ] Per-category bonus (e.g. `category_bonus_fun_minutes`) adds to that category's limit when `category_bonus_fun_date == today`
- [ ] Bonus does not carry over to next day (date check gates it)
- [ ] Multiple per-category bonuses can be active simultaneously for different categories
- [ ] Global bonus + per-category bonus can both be active; each applies to its respective limit

#### 4.3 Bonus time request flow
- [ ] If per-category bonus requested via Telegram, `category_bonus_*_status` tracks pending/granted/denied
- [ ] `GET /api/time-request-status` returns per-category bonus status alongside global bonus status
- [ ] Granting category bonus updates `category_bonus_fun_minutes` AND `category_bonus_fun_date`

---

### 5. Backend — API Endpoint Contract

#### 5.1 `GET /api/time-status` (or new endpoint)
- [ ] Response includes global fields (existing): `limit_min`, `used_min`, `remaining_min`, `remaining_sec`, `exceeded`
- [ ] Response includes new per-category data — expected shape:
  ```json
  {
    "categories": {
      "fun": { "limit_min": 60, "used_min": 25.5, "remaining_min": 34.5, "remaining_sec": 2070, "exceeded": false },
      "edu": { "limit_min": 90, "used_min": 90.0, "remaining_min": 0.0, "remaining_sec": 0, "exceeded": true }
    }
  }
  ```
- [ ] Categories with no limit configured are omitted OR returned with `limit_min: 0` / `remaining_sec: -1` (verify convention with frontend dev)
- [ ] Free day: all category `remaining_sec` return `-1` (free day sentinel)
- [ ] Endpoint returns 404 for unknown `child_id`
- [ ] Endpoint returns 401 without auth

#### 5.2 Heartbeat response — remaining seconds
- [ ] `POST /api/heartbeat` returns `remaining` reflecting the **most restrictive** of:
  - Global daily remaining seconds
  - Current video's category remaining seconds
- [ ] If global limit not set but category limit set, category limit is used
- [ ] If category limit not set but global limit set, global limit is used
- [ ] If neither is set, returns `-1` (unrestricted)

---

### 6. Backend — Most-Restrictive-Wins Logic

- [ ] Child has `global_limit = 60 min`, `category_limit_fun = 30 min`. After 30 min of "fun": heartbeat returns remaining = 0 (category blocks, even though 30 global minutes remain)
- [ ] Child has `global_limit = 30 min`, `category_limit_fun = 60 min`. After 30 min total: heartbeat returns remaining = 0 (global blocks)
- [ ] Child switches to "edu" video after "fun" is exhausted: edu category budget is checked; if edu has remaining time and global has remaining time, playback is allowed
- [ ] "fun" exhaustion does not affect "edu" budget
- [ ] Global daily exhaustion blocks ALL categories regardless of per-category budgets

---

### 7. Backend — Free Day Override

- [ ] When `free_day_date == today`, `GET /api/time-status` returns `remaining_sec = -1` for global limit
- [ ] When free day active, all category `remaining_sec` also return `-1`
- [ ] Heartbeat returns `-1` on free day (no blocking)
- [ ] Free day set via existing mechanism — verify category limits do not override free day

---

### 8. Backend — Backward Compatibility

- [ ] Child with no category limits configured: `GET /api/time-status` returns same response as before (no `categories` field, or `categories: {}`)
- [ ] Existing `/api/heartbeat` behavior unchanged when no category limits set
- [ ] `watch_log` rows inserted before migration (no `category` column) are treated as `category = 'fun'` after migration
- [ ] Children with only a global limit and no category limits: global limit enforced as before

---

### 9. Frontend (tvOS) — Category Time Display

#### 9.1 Sidebar time buttons
- [ ] Sidebar shows a time button per configured category
- [ ] Each button displays formatted remaining time (e.g. "45m", "1h 15m")
- [ ] Button label includes the category name (e.g. "Fun: 45m", "Edu: 1h 15m")
- [ ] Unrestricted categories (no limit set) show no time button, OR show "Unlimited"
- [ ] Free day: all category buttons show "Free day!" or equivalent

#### 9.2 Exhausted category dimming
- [ ] When a category's remaining time is 0, its sidebar button is dimmed/disabled
- [ ] Dimming applied correctly without affecting other categories
- [ ] Un-dimmed on new day (limit resets)

#### 9.3 Bonus badge
- [ ] Bonus badge visible on category button when a bonus is active
- [ ] Badge shows bonus amount (e.g. "+15m")
- [ ] Badge disappears when bonus expires (next day)

---

### 10. Frontend (tvOS) — Playback Blocking and Overlays

#### 10.1 Category exhaustion overlay
- [ ] When the active video's category limit is exhausted, a category-exhaustion overlay is shown (distinct from global time-up overlay)
- [ ] Overlay text names the exhausted category (e.g. "You've used all your Fun time today")
- [ ] Overlay offers "Request more time" action for the specific category

#### 10.2 Correct overlay for each exhaustion type
- [ ] Global limit exhausted → shows global TimesUp overlay (existing behavior)
- [ ] Category limit exhausted (but global remaining) → shows category exhaustion overlay
- [ ] Both exhausted simultaneously → shows global TimesUp overlay (most severe)
- [ ] No incorrect overlay shown for unrestricted categories

#### 10.3 Playback blocking
- [ ] Playback does not start when the active video's category is exhausted
- [ ] Player presents category exhaustion overlay before stream request if category is already over limit
- [ ] Mid-video: heartbeat returns 0 remaining → wind-down then stop (same wind-down UX as global limit)

#### 10.4 Wind-down integration
- [ ] Category exhaustion triggers the same wind-down warning as global limit (last N seconds warning)
- [ ] Wind-down fires based on the most-restrictive remaining time (whichever is smaller: global or category)

---

### 11. Frontend (tvOS) — Unrestricted Categories

- [ ] Videos in categories with no limit set play without category-related blocking
- [ ] Sidebar shows no (or "Unlimited") indicator for uncapped categories
- [ ] Uncapped category videos still count toward global daily limit

---

### 12. Integration — API Contract Alignment

- [ ] Swift model (`CategoryTimeStatus` or equivalent) matches server JSON field names exactly (snake_case → camelCase via `CodingKeys`)
- [ ] `TimeStatus` struct extended (or new struct added) to include `categories` dictionary
- [ ] `APIClient` calls the correct endpoint URL for category time data
- [ ] If server returns no `categories` field, Swift decodes gracefully (empty dict or optional)
- [ ] `HeartbeatResponse.remaining` semantics match: `-1` = unrestricted, `0` = blocked, `>0` = seconds remaining

---

### 13. Edge Cases

#### 13.1 Video with no category
- [ ] Video whose channel has `category = NULL` is treated as `'fun'` in watch_log and in limit checks
- [ ] Edge case: channel category set to empty string `""` — treated same as NULL (`'fun'`)

#### 13.2 New category limit set mid-day
- [ ] If parent sets a new category limit mid-day, the child's already-watched time for that category is immediately applied to the new limit
- [ ] No double-counting: watch_log rows from before limit was set count toward the limit

#### 13.3 Category limit set to exactly current usage
- [ ] Setting limit = current usage → `exceeded = True`, `remaining_sec = 0` immediately
- [ ] Child is blocked on next video start in that category

#### 13.4 All categories exhausted
- [ ] All configured category limits hit but global limit not hit: child cannot start any video
- [ ] Home screen / category tabs reflect all-categories-exhausted state appropriately
- [ ] Child can still navigate UI (not completely locked out)

#### 13.5 Global daily limit exhausted but category budget remains
- [ ] Global TimesUp overlay shown (not category exhaustion overlay)
- [ ] Per-category remaining time displayed correctly (non-zero) but child still blocked

#### 13.6 Heartbeat edge cases
- [ ] Heartbeat with `seconds = 0` does not create a watch_log row (or creates a no-op row with 0 duration)
- [ ] Rapid heartbeats (multiple per second) don't corrupt category totals

#### 13.7 Child with no watch log yet today
- [ ] `used_min = 0` for all categories
- [ ] `exceeded = False` for all categories
- [ ] `remaining_sec = limit_min * 60` for all configured categories

---

## Test Execution Plan

### Server Tests (`server/tests/`)

New test file: `server/tests/test_category_time_limits.py`

Planned test classes:
1. `TestCategoryWatchLogMigration` — migration adds column, is idempotent, backfills safely
2. `TestCategorySettings` — CRUD for category limit settings via VideoStore
3. `TestCategoryTimeComputation` — `get_daily_watch_minutes` with category filter
4. `TestCategoryBonusTime` — bonus stacking logic
5. `TestCategoryTimeStatusEndpoint` — full API response shape via TestClient
6. `TestHeartbeatCategoryIntegration` — heartbeat writes category, response reflects most-restrictive
7. `TestMostRestrictiveWins` — parametrized cases for limit interaction
8. `TestFreeDay` — free day overrides all category limits
9. `TestBackwardCompat` — no category limits configured → existing behavior unchanged

### tvOS Tests (`tvos/Tests/`)

New test file: `tvos/Tests/CategoryTimeLimitTests.swift`

Planned test cases:
1. `testCategoryTimeStatusDecoding` — JSON → Swift model round-trip
2. `testCategoryTimeStatusDecodingMissingCategories` — graceful decode with no `categories` field
3. `testFormattedRemainingForCategory` — helper format strings (0m, 45m, 1h 15m, Free day!)
4. `testMostRestrictiveHeartbeatRemaining` — logic that picks smaller of global vs category remaining
5. `testExhaustedCategoryDetection` — `exceeded: true` maps correctly in model

### Existing Test Suites

Must continue to pass with no regressions:
- `server/tests/test_api.py` — auth, profiles, stream, heartbeat
- `server/tests/test_video_store.py` — all VideoStore tests
- `server/tests/test_session_windowing.py` — session state logic
- `tvos/Tests/` — all existing swift tests

---

## Key Risk Areas

| Risk | Severity | Mitigation |
|------|----------|------------|
| Migration backfill logic: NULL category vs 'fun' default — inconsistent treatment could cause under/over-counting | High | Test migration on DB with existing rows; verify query treats NULL == 'fun' |
| Global + category bonus stacking: spec unclear on whether global bonus also extends category budgets | High | Confirm with backend-dev before Phase 2; flag in report |
| Most-restrictive-wins computation in heartbeat: must check both limits on every tick | High | Parametrized tests covering all four combinations (global limited/unlimited × category limited/unlimited) |
| Category exhaustion overlay vs global TimesUp overlay: wrong overlay shown | Medium | Verify frontend-dev implements distinct overlay paths; test all four exhaustion states |
| Free day sentinel value (-1 for remaining_sec): must propagate to ALL category entries | Medium | Dedicated free day test; assert every category entry shows -1 |
| Watch_log category NULL handling in SQL SUM: `WHERE category = 'fun'` won't match NULLs | Medium | Backend must use `COALESCE(category, 'fun') = 'fun'` or equivalent |
| Heartbeat race: child switches video categories mid-session; wrong category used for limit check | Low | Test heartbeat with video_id that resolves to different category than previous |

---

## Deferred (Out of Scope for Issue #6)

- Multi-level category hierarchy (e.g. "science" as a subcategory of "edu")
- Parental dashboard showing category usage history
- Push notifications when a category budget is nearly exhausted
- Per-session (not per-day) category limits
