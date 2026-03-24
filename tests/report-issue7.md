# QA Integration Report — Issue #7: UI/UX Overhaul

**Date:** 2026-03-23
**Issue:** #7 — UI/UX overhaul for the tvOS app

## Summary

The backend and frontend implementations are well-aligned. No critical integration bugs found. Three minor findings documented below. All tests pass (30 new backend, 126 tvOS including 8 new). The code is ready for merge.

---

## Files Reviewed

### Backend (server/)
- `server/api/models.py` — New `RecentlyAddedResponse`, `ChannelDetailResponse` models
- `server/api/routes.py` — New `GET /api/recently-added` and `GET /api/channels/{channel_id}` endpoints
- `server/data/video_store.py` — New `get_recently_added_videos()`, `get_channel_video_count()` methods
- `server/tests/test_recently_added_endpoint.py` — 30 tests covering both new endpoints

### Frontend (tvos/)
- `tvos/Sources/App/ContentView.swift` — Updated: sidebar layout, section routing, channel browsing
- `tvos/Sources/Views/Sidebar/SidebarView.swift` — **New:** Plex-style sidebar with Home, Channels, Categories, Search, Profile
- `tvos/Sources/Views/Theme/AppTheme.swift` — **New:** Design tokens (surfaces, text, cards, category colors, skeleton loaders)
- `tvos/Sources/Views/Profile/ProfileView.swift` — **New:** Child info, time progress bar, switch profile
- `tvos/Sources/Views/Channels/ChannelsListView.swift` — **New:** Channel grid with skeleton loading
- `tvos/Sources/Views/Categories/CategoryContentView.swift` — **New:** Category-filtered video grid with sort controls
- `tvos/Sources/Views/Search/SidebarSearchView.swift` — **New:** Search screen with video/channel results
- `tvos/Sources/Views/Components/VideoCard.swift` — **Updated:** badge support, progress bar, watched state, FocusScaleModifier
- `tvos/Sources/Views/Components/ChannelCard.swift` — **New:** Circular avatar card for search results
- `tvos/Sources/Views/Components/TimeBadge.swift` — **New:** Remaining time badge with color-coded states
- `tvos/Sources/Views/Home/HomeView.swift` — **Updated:** Recently Added row integration
- `tvos/Sources/Models/APIResponses.swift` — New `RecentlyAddedResponse`, `ChannelDetailResponse` models
- `tvos/Sources/Services/APIClient.swift` — New `getRecentlyAdded()`, `getChannelDetail()` methods
- `tvos/Tests/UIOverhaulTests.swift` — 8 new tests

---

## Check Results

### 1. API Endpoint Alignment

| Endpoint | Frontend Call | Backend Route | Result |
|----------|-------------|---------------|--------|
| Recently Added | `getRecentlyAdded(childId:limit:)` → `GET /api/recently-added` | `@router.get("/recently-added")` | PASS |
| Channel Detail | `getChannelDetail(channelId:childId:offset:limit:)` → `GET /api/channels/{channelId}` | `@router.get("/channels/{channel_id}")` | PASS |
| Auth header (Bearer token) sent on both | — | — | PASS |
| `child_id` required on both endpoints | — | — | PASS |

### 2. Request/Response Model Alignment

**RecentlyAddedResponse:**

| Backend Field | Frontend Field | CodingKey | Result |
|------|------|------|------|
| `videos: list[dict]` | `videos: [Video]` | — | PASS |

Backend dicts include `video_id`, `title`, `channel_name`, `effective_category`, `watch_position`, `watch_duration`, `watch_status`, `access_decided_at`. Frontend `Video` model has CodingKeys for all of these. **PASS**

**ChannelDetailResponse:**

| Backend Field | Frontend Field | CodingKey | Result |
|------|------|------|------|
| `channel_name: str` | `channelName: String` | `"channel_name"` | PASS |
| `channel_id: str` | `channelId: String?` | `"channel_id"` | PASS (frontend more permissive) |
| `handle: Optional[str]` | `handle: String?` | `"handle"` | PASS |
| `category: Optional[str]` | `category: String?` | `"category"` | PASS |
| `thumbnail_url: Optional[str]` | `thumbnailUrl: String?` | `"thumbnail_url"` | PASS |
| `banner_url: Optional[str]` | `bannerUrl: String?` | `"banner_url"` | PASS |
| `video_count: int` | `videoCount: Int` | `"video_count"` | PASS |
| `videos: list[dict]` | `videos: [Video]` | — | PASS |
| `has_more: bool` | `hasMore: Bool` | `"has_more"` | PASS |
| `total: int` | `total: Int` | `"total"` | PASS |

### 3. Sidebar Navigation Wiring

| Sidebar Section | Target View | API Call | Result |
|----------------|-------------|----------|--------|
| Home | `HomeView` | `getRecentlyAdded()`, `getHomeChannels()`, `getCatalog()`, `getTimeStatus()`, `getScheduleStatus()` | PASS |
| Channels | `ChannelsListView` | `getHomeChannels()` | PASS |
| Channels → select | `ChannelDetailView` | `getChannelVideos()` (existing endpoint) | PASS |
| Educational | `CategoryContentView` | `getCatalog(category: "edu")` | PASS |
| Entertainment | `CategoryContentView` | `getCatalog(category: "fun")` | PASS |
| Search | `SidebarSearchView` | `search()` (existing endpoint) | PASS |
| Profile | `ProfileView` | No API calls (receives `timeStatus` from parent) | PASS |

### 4. Data Layer

| Check | Result |
|-------|--------|
| `get_recently_added_videos()` filters by `status = 'approved'` | PASS |
| `get_recently_added_videos()` excludes blocked channels (`COALESCE(ch.status, 'allowed') != 'blocked'`) | PASS |
| `get_recently_added_videos()` orders by `decided_at DESC NULLS LAST` | PASS |
| `get_recently_added_videos()` includes watch metadata (position, duration, status) | PASS |
| `get_recently_added_videos()` includes `effective_category` via COALESCE | PASS |
| Per-child isolation on both endpoints | PASS |
| Channel detail uses defense-in-depth channel filter (matches both `channel_name` and `channel_id`) | PASS |
| Limit validation: recently-added `ge=1, le=50`; channel-detail `ge=1, le=100` | PASS |

### 5. Error Handling

| Check | Result |
|-------|--------|
| Recently-added: 404 for invalid `child_id` | PASS |
| Recently-added: 422 for missing `child_id` | PASS |
| Channel detail: 400 for invalid channel ID format (non-UC) | PASS |
| Channel detail: 404 for invalid `child_id` | PASS |
| Channel detail: 422 for missing `child_id` | PASS |
| Channel detail: gracefully handles Invidious failures (logs warning, returns null metadata) | PASS |
| Frontend `loadRecentlyAdded` silently catches errors (non-critical row) | PASS |
| Frontend `ChannelsListView` shows error message on load failure | PASS |
| Frontend `CategoryContentView` shows error message on load failure | PASS |

### 6. Theme & Focus Consistency

| Check | Result |
|-------|--------|
| `AppTheme.categoryColor()` maps edu→blue, fun→green, music→purple, science→orange, art→pink, fallback→teal | PASS |
| `SkeletonLoader` uses shimmer animation (1.5s linear repeat) | PASS |
| `VideoCardSkeleton` used in loading states for search, category, channels | PASS |
| `VideoCard` uses `FocusScaleModifier` with `AppTheme.cardFocusScale` (1.05) | PASS |
| `ChannelsListItemView` uses focus glow with `AppTheme.cardFocusGlowColor` | PASS |
| `TimeBadge` color-codes by remaining time (normal→black, ≤10min→orange, exceeded→red, free day→green) | PASS |
| Sidebar items show selection state via `AppTheme.sidebarSelectedBackground` | PASS |

### 7. Test Coverage

| Check | Result |
|-------|--------|
| Server: 30 new tests pass (`test_recently_added_endpoint.py`) | PASS |
| tvOS: 126 tests pass (8 new in `UIOverhaulTests.swift`) | PASS |
| Recently-added: auth, child validation, empty list, video list, params, error handling | PASS |
| Channel detail: auth, validation, metadata, pagination, per-child, category source | PASS |
| RecentlyAddedResponse model decode tests (with videos, empty) | PASS |

### 8. Project Structure

| Check | Result |
|-------|--------|
| `project.yml` uses directory sources — new files auto-included | PASS |
| `Package.swift` correctly excludes `Views/` and `App/` from test target | PASS |
| All new Views files have `import SwiftUI` only (no external deps) | PASS |

---

## Findings

### FINDING 1: `getChannelDetail()` defined but unused (Info — not a bug)

**Location:** `tvos/Sources/Services/APIClient.swift:84-98`

The frontend defines `getChannelDetail()` and `ChannelDetailResponse`, and the backend implements `GET /api/channels/{channel_id}` — but no view calls `getChannelDetail()`. The `ChannelDetailView` still uses the pre-existing `getChannelVideos()` which hits `GET /api/channel/{channel_id}/videos`.

This is documented in the test plan and appears intentional — the new endpoint is ready for a future migration. The `ChannelDetailResponse` model and `getChannelDetail()` method are dead code for now.

**Impact:** None. The old endpoint works correctly. The new endpoint is available for future use.

### FINDING 2: `video_count` vs `total` potential mismatch in ChannelDetailResponse (Minor)

**Location:** `server/api/routes.py:837` and `server/data/video_store.py:737-747`

`video_count` comes from `get_channel_video_count()` which filters only by `v.channel_id = ?`. But `total` comes from `get_approved_videos()` which filters by `(v.channel_name = ? COLLATE NOCASE OR v.channel_id = ?)`.

If a video exists with a matching `channel_name` but no `channel_id`, it would be counted in `total` but not in `video_count`, resulting in `video_count < total`.

**Impact:** Minimal — this endpoint isn't currently used by the frontend, and the edge case only occurs with legacy data where `channel_id` wasn't stored. When the endpoint is eventually wired up, `get_channel_video_count()` should be updated to match both `channel_name` and `channel_id` for consistency.

### FINDING 3: Sidebar hardcodes only 2 categories (Design note)

**Location:** `tvos/Sources/Views/Sidebar/SidebarView.swift:50-62`

The sidebar shows only "Educational" (edu) and "Entertainment" (fun) categories. `AppTheme.categoryColor()` supports additional categories: music (purple), science (orange), art/creative (pink). Videos with those categories are still accessible via the Home catalog and category filter buttons, but aren't directly navigable from the sidebar.

**Impact:** Design choice, likely intentional for MVP. Worth noting for future enhancement.

---

## Post-Review Fix Verification (2026-03-24)

Frontend-dev fixed 3 navigation/focus bugs. All verified:

- **Focus trapped in sidebar (FIXED):** Added `.focusSection()` to sidebar container (`SidebarView.swift:93`) and content pane (`ContentView.swift:74`). tvOS focus engine now treats them as separate focus regions — D-pad right/left correctly moves between sidebar and content.
- **Profile switch shows wrong tab (FIXED):** Added `.onChange(of: selectedChild?.id)` in `ContentView.swift:28-32` that resets `sidebarSection = .home` and clears `browsingChannel` on profile change. New profile always opens to Home tab.

All 126 tvOS tests pass.

### Sidebar overflow fix (2026-03-24)

Frontend-dev fixed "Entertainment" label overflow in `SidebarItemView` (`SidebarView.swift`). All verified:

- **`.lineLimit(1)`** (line 174) — prevents text wrapping when focus scaling expands content
- **`.frame(height: 52)`** (line 179) — fixed row height prevents vertical shifting on focus changes
- **`.clipShape(Rectangle())`** (line 185) — clips overflow from focus-induced scaling
- **`isFocused || isSelected`** (line 182) — background highlight now shows on focus too, not just selection

All 126 tvOS tests pass.

---

## Overall Assessment

The UI/UX overhaul implementation is well-structured and thoroughly tested. All new views, API endpoints, and models are correctly wired together. The sidebar navigation properly routes to all sections. Error handling is comprehensive — errors in non-critical features (recently added, channels) are silently caught while errors in critical features (catalog, search) are displayed to the user. Theme tokens are consistently applied throughout.

No critical integration bugs found. The three findings are all minor/informational.

**Status: Ready for merge.**
