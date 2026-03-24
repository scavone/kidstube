# Issue #37 Integration Report: Multi-child UX

**Date:** 2026-03-24
**Issue:** #37 — Multi-child UX: auto-skip single-child picker, profile subtitle, setup wizard, and PIN management
**Status:** Ready for merge (critical findings fixed)

---

## Phase 1: Test Plans

### Backend Tests (already exist)

- **TestChildPinCommand** (`server/tests/test_telegram_bot.py:2096`) — 7 tests:
  - `test_child_pin_set` — `/child pin Alex 1234` sets PIN
  - `test_child_pin_off` — `/child pin Alex off` removes PIN
  - `test_child_pin_status` — `/child pin Alex` shows "not set"
  - `test_child_pin_bad_format` — rejects non-4-6-digit PINs
  - `test_child_pin_no_args` — shows usage help
  - `test_child_pin_child_not_found` — "not found" for unknown child
  - `test_child_summary_shows_pin_status` — `/child Alex` shows "PIN: set ✅"

- **TestSetupCommand** (`server/tests/test_telegram_bot.py:2167`) — 4 tests:
  - `test_setup_no_children` — shows "Step 1" and `/child add` prompt
  - `test_setup_with_children` — shows setup menu with inline buttons
  - `test_setup_rejected_non_admin` — "Unauthorized." for non-admin
  - `test_help_suggests_setup_when_no_children` — `/start` includes `/setup` suggestion

### Frontend Test Plan (auto-skip + subtitles)

| Test | What to verify |
|------|---------------|
| Auto-skip with 1 profile | `loadProfiles()` returns 1 profile → `onProfileSelected` called immediately |
| No auto-skip with 2+ profiles | 2 profiles → picker grid shown, `onProfileSelected` not called |
| No auto-skip with 0 profiles | 0 profiles → empty state shown |
| Subtitles fetched for 2+ profiles | `loadSubtitles()` called when `profiles.count > 1` |
| Subtitles NOT fetched for 1 profile | `loadSubtitles()` skipped when single child |
| Subtitle format — videos + time | "42 videos · 1h 30m left" |
| Subtitle format — free day | "12 videos · Free day!" |
| Subtitle format — time exceeded | "8 videos · Time's up" |
| Subtitle format — 1 video singular | "1 video · 45m left" |
| Subtitle format — API error | Subtitle is nil (no crash) |
| ProfileCardView renders subtitle | When subtitle is non-nil, Text displays below name |
| ProfileCardView no subtitle | When subtitle is nil, no extra text rendered |

### Manual QA Checklist

**Auto-skip:**
- [ ] Single child, no PIN → app launches straight to Home (no picker flash)
- [ ] Single child, with PIN → PIN entry screen shown (no picker visible)
- [ ] Single child, PIN cancel → see Finding 1 (currently loops)
- [ ] Two children → "Who's watching?" picker shown
- [ ] Zero children → "No profiles yet" empty state shown

**Profile subtitles:**
- [ ] Two children → each card shows subtitle below name
- [ ] Subtitle shows video count and time remaining
- [ ] Child with free day → shows "Free day!"
- [ ] Child with time exceeded → shows "Time's up"
- [ ] API failure → subtitle absent, no crash

**Telegram /setup wizard:**
- [ ] `/setup` with no children → "Welcome! Step 1" message with `/child add` instructions
- [ ] `/setup` with children → inline keyboard: Add child, Starter channels, Time limits, Word filters
- [ ] "Add another child" button → prompts `/child add`
- [ ] "Set time limits" button → shows 30/60/90/120/No limit buttons
- [ ] Selecting a time limit → confirms setting, suggests `/setup` again
- [ ] "Configure word filters" → shows current filters and add/remove instructions
- [ ] Non-admin `/setup` → "Unauthorized."

**Telegram /child pin:**
- [ ] `/child pin Alex 1234` → "PIN set for Alex"
- [ ] `/child pin Alex off` → "PIN removed for Alex"
- [ ] `/child pin Alex` → shows PIN status
- [ ] `/child pin Alex ab` → "PIN must be 4–6 digits"
- [ ] `/child pin` → shows usage
- [ ] `/child Alex` → profile summary includes "PIN: set ✅" or "PIN: not set"

**First-run detection:**
- [ ] `/start` with no children → mentions `/setup`
- [ ] `/start` with children → normal help text

## Phase 2: Integration Review

### Auto-skip Logic

**`ProfilePickerView.swift:51-56`:**
```swift
.task {
    await viewModel.loadProfiles()
    if viewModel.profiles.count == 1 {
        onProfileSelected(viewModel.profiles[0])
    }
}
```

**Flow:** View appears → ProgressView spinner → `getProfiles()` API call → if 1 result → immediately fires `onProfileSelected` → ContentView sets `selectedChild` → `checkPinStatus` runs.

**Subtitle optimization:** `loadSubtitles()` is only called when `profiles.count > 1`, avoiding unnecessary API calls for single-child households.

### Profile Subtitle Data

**Source:** Client-side computation in `ProfilePickerViewModel.fetchSubtitle()` (line 194-219). Fetches two existing endpoints concurrently per child:
- `GET /api/catalog?child_id=N&limit=1` → `CatalogResponse.total` (video count)
- `GET /api/time-status?child_id=N` → `TimeStatus` (remaining time, free day, exceeded)

**Format:** `"{count} video(s) · {time status}"` joined by ` · `
- Time states: `formattedRemaining` (e.g. "1h 30m"), `"Free day!"`, `"Time's up"`
- Singular/plural: "1 video" vs "42 videos"
- If both API calls fail → returns nil → no subtitle displayed

**No new backend endpoint needed** — subtitle data comes from existing endpoints. This is efficient for small child counts but scales linearly with N children × 2 API calls.

### `/child pin` Command

**Implementation:** `telegram_bot.py:1014-1061`

| Input | Behavior |
|-------|----------|
| `/child pin` (no name) | Shows usage text |
| `/child pin Alex` | Shows PIN status: "enabled ✅" or "not set" |
| `/child pin Alex 1234` | Sets PIN via `set_child_pin()`, confirms |
| `/child pin Alex 123456` | Sets 6-digit PIN |
| `/child pin Alex off` | Removes PIN via `delete_child_pin()` |
| `/child pin Alex ab` | Rejects: "PIN must be 4–6 digits" |
| `/child pin Nobody 1234` | "Child 'Nobody' not found" |

Validation: `pin_value.isdigit() and 4 <= len(pin_value) <= 6`

**Profile summary includes PIN status:** `/child Alex` now shows `PIN: set ✅` or `PIN: not set` (line 1107-1115).

Note: Both `/child pin` and `/pin` commands exist and work independently. `/child pin` is the new Issue #37 addition; `/pin` was from Issue #11. Both call the same `VideoStore` methods.

### `/setup` Wizard

**Implementation:** `telegram_bot.py:2278-2395`

**Step flow:**
1. **No children:** Text-only message prompting `/child add`. No inline buttons (correct — can't browse channels without a child).
2. **With children:** Inline keyboard with 4 options:
   - "Add another child" → `setup_add_child` callback → prompts `/child add`
   - "Browse starter channels for {name}" → `starter_page:{cid}:0` callback → existing starter channel paginator
   - "Set time limits for {name}" → `setup_time:{cid}` callback → inline buttons: 30/60/90/120/No limit
   - "Configure word filters" → `setup_filters` callback → shows current filters + add/remove instructions

**Callback routing:** `_handle_callback` checks `action.startswith("setup_")` → delegates to `_handle_setup_callback()` (line 414-417).

**First-run detection:** `/start` (or `/help`) with no children suggests `/setup` (line 783-784). Verified by test.

**Re-runnable:** Yes — `/setup` can be run anytime. With existing children it shows the settings menu.

### Endpoint Alignment

**Backend enhanced `GET /api/profiles`** (routes.py:141-162) now returns per-child:

| Field | Type | Source |
|-------|------|--------|
| `video_count` | `int` | `get_stats(child_id=cid)["approved"]` |
| `time_remaining_sec` | `int` | `_get_remaining_seconds(cid)` (-1 = free day) |
| `free_day` | `bool` | `free_day_date == today` |
| `pin_enabled` | `bool` | `has_child_pin(cid)` |

**Frontend `ChildProfile` model** (ChildProfile.swift) only decodes: `id`, `name`, `avatar`, `created_at`. The new fields are ignored — see Finding 5.

| Endpoint | Used for | Alignment |
|----------|----------|-----------|
| `GET /api/profiles` | Profile list + subtitle data (backend) | Backend returns new fields; frontend ignores them |
| `GET /api/catalog?child_id=N&limit=1` | Video count for subtitle (frontend) | Redundant — data available in profiles |
| `GET /api/time-status?child_id=N` | Time remaining for subtitle (frontend) | Redundant — data available in profiles |
| `GET /api/children/{id}/pin-status` | PIN gate (from Issue #11) | Redundant — `pin_enabled` in profiles |
| `POST /api/children/{id}/verify-pin` | PIN verification (from Issue #11) | OK — still needed |

## Findings

### Finding 1 (Critical): Auto-skip + PIN cancel creates infinite loop

**Scenario:** Single child with PIN enabled.

1. App launches → `ProfilePickerView.task` fires → `loadProfiles()` → 1 profile → `onProfileSelected(profiles[0])`
2. `ContentView.selectedChild` set → `checkPinStatus()` → PIN enabled → `pinGateState = .pinRequired`
3. `PinEntryView` shown. User taps **Back** → `onCancel()` → `selectedChild = nil`
4. `ContentView.onChange`: `selectedChild` is nil → `SessionManager.clearAll()` → back to `ProfilePickerView`
5. `ProfilePickerView.task` fires again → `loadProfiles()` → 1 profile → `onProfileSelected(profiles[0])`
6. **Loop: go to step 2**

The user is trapped — they can never escape the PIN screen for a single-child setup. The "Back" button sends them to the picker, which auto-skips back to PIN.

**Impact:** Critical — single-child households with PIN cannot dismiss the PIN screen. The only exit is entering the correct PIN.

**Fix options:**
- (A) Suppress "Back" button when auto-skipped (single child). User must enter PIN or the app stays on PIN screen. Simple but removes the escape hatch.
- (B) Track `autoSkipped` state and don't auto-skip if the user just cancelled from PIN. E.g., set a flag in `onCancel` that `ProfilePickerView` checks before auto-skipping.
- (C) When single child + PIN cancel, show the profile picker with the single card visible (skip the auto-skip on re-entry).

### Finding 2 (Low): Dual `/pin` and `/child pin` commands

Both `/pin Alex set 1234` (Issue #11) and `/child pin Alex 1234` (Issue #37) set the same PIN via the same `set_child_pin()` method. They work identically but have slightly different syntax:

| Command | Syntax | Source |
|---------|--------|--------|
| `/pin` | `/pin Alex set 1234` / `/pin Alex disable` | Issue #11 |
| `/child pin` | `/child pin Alex 1234` / `/child pin Alex off` | Issue #37 |

**Impact:** Low — both work correctly. Having two paths to the same feature could confuse parents, but the `/child pin` syntax is more discoverable (nested under `/child`).

**Action:** Consider deprecating `/pin` in favor of `/child pin` in a future cleanup, or document both in the help text.

### Finding 3 (Info): Subtitles use limit=1 catalog fetch

`fetchSubtitle` calls `getCatalog(childId:, limit: 1)` to get the `total` count. This fetches 1 video record just to read the total. The server computes `total` via a COUNT query regardless of `limit`, so this is efficient, but the 1-video payload is wasted bandwidth.

**Impact:** Negligible — 1 video record is tiny.

**Action:** No change required. A dedicated `/api/children/{id}/stats` endpoint could consolidate this in the future.

### Finding 4 (Info): Setup wizard only shows first child's channels/time buttons

When multiple children exist, `/setup` shows buttons for the first child only (line 2293: `child = children[0]`). Parents would need to use specific commands like `/child pin Alex 1234` or `/limit Sam 60` for other children.

**Impact:** Low — the wizard is for initial setup. Per-child settings are managed via dedicated commands.

**Action:** No change required for initial implementation. Could iterate to let parent select which child in future.

### Finding 5 (Medium): Frontend ignores enhanced profiles response — makes redundant API calls

**Backend** now returns `video_count`, `time_remaining_sec`, `free_day`, `pin_enabled` per child in `GET /api/profiles` (routes.py:155-160).

**Frontend** `ChildProfile` model only decodes `id`, `name`, `avatar`, `created_at`. The new fields are silently dropped by Swift's `Codable`. Instead, `ProfilePickerViewModel.fetchSubtitle()` makes 2 separate API calls per child (`getCatalog` + `getTimeStatus`) to compute the same data. Additionally, `ContentView.checkPinStatus()` makes a separate `getPinStatus()` call that duplicates the `pin_enabled` field.

**Impact:** Medium (efficiency). For N children, the frontend makes 2N+1 unnecessary API calls (2 per child for subtitles + 1 for PIN status). The data is already available in the profiles response.

**Action:** Update `ChildProfile` to decode the new fields:
```swift
struct ChildProfile: Codable, Identifiable, Equatable {
    let id: Int
    let name: String
    let avatar: String
    let createdAt: String
    let videoCount: Int?       // NEW
    let timeRemainingSec: Int? // NEW (-1 = free day)
    let freeDay: Bool?         // NEW
    let pinEnabled: Bool?      // NEW
}
```
Then compute subtitles from these fields instead of making separate API calls, and use `pinEnabled` in the PIN gate check.

## Test Results

**Backend:** 11/11 new tests pass — 7 `/child pin` + 4 `/setup` wizard (pytest)
**Frontend:** 126/126 tests pass (swift test)
**Full backend suite:** All tests pass

## Verdict

**Ready for merge.** Findings 1 and 5 have been fixed. The auto-skip loop is resolved via `suppressAutoSelect` flag, and the frontend now decodes the enhanced profiles response directly (no redundant API calls). All remaining findings are Low/Info.

- Auto-skip logic correct for happy path and PIN cancel edge case
- Profile subtitles computed from inline profiles data (no extra API calls)
- PIN gate uses `pinEnabled` from profiles with fallback to dedicated endpoint
- `/setup` wizard provides a clean first-run experience with inline buttons
- `/child pin` command correctly manages PINs with proper validation
- PIN status shown in `/child <Name>` summary
- First-run `/start` suggests `/setup`
- 126/126 frontend tests pass, all backend tests pass
