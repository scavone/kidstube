# QA Integration Report — Issue #3: Home Screen Redesign

**Date:** 2026-03-23
**Issue:** [#3 — Redesign TV app home screen with channel row and featured banner](https://github.com/scavone/yt4kids/issues/3)

## Summary

The backend and frontend implementations are well-structured and mostly aligned. Two integration bugs were found — one that will cause the channel catalog filter to return empty results, and one UI label mismatch. All existing tests pass (533 server, 120 tvOS).

---

## Files Reviewed

### Backend (server/)
- `server/api/models.py` — New `LatestVideoResponse`, `ChannelHomeItem`, `ChannelsHomeResponse` models
- `server/api/routes.py` — New `GET /api/channels-home` endpoint
- `server/data/video_store.py` — New `get_channels_with_latest_video()` method
- `server/invidious/client.py` — Extended `get_channel_info()` with `thumbnail_url` and `banner_url`
- `server/tests/test_api.py` — 5 new tests for `TestChannelsHomeEndpoint`
- `server/tests/test_video_store.py` — 7 new tests for `TestChannelsWithLatestVideo`

### Frontend (tvos/)
- `tvos/Sources/Models/HomeChannel.swift` — New `HomeChannel`, `HomeChannelVideo`, `HomeChannelsResponse` models
- `tvos/Sources/Services/APIClient.swift` — New `getHomeChannels(childId:)` method
- `tvos/Sources/Views/Home/HomeView.swift` — Refactored layout with banner + channel row + catalog
- `tvos/Sources/Views/Home/FeaturedBannerView.swift` — New featured banner view
- `tvos/Sources/Views/Home/HomeChannelRowView.swift` — New channel row view

---

## Check Results

### 1. API Endpoint Alignment
| Check | Result |
|-------|--------|
| Frontend calls `GET /api/channels-home` | PASS |
| Backend defines `GET /api/channels-home` under auth router | PASS |
| Query param `child_id` used consistently | PASS |
| Auth header (Bearer token) sent by APIClient | PASS |

### 2. Request/Response Model Alignment

| Backend Field (ChannelHomeItem) | Frontend Field (HomeChannel) | CodingKey | Result |
|------|------|------|------|
| `channel_name: str` | `channelName: String` | `"channel_name"` | PASS |
| `channel_id: Optional[str]` | `channelId: String?` | `"channel_id"` | PASS |
| `handle: Optional[str]` | `handle: String?` | `"handle"` | PASS |
| `category: Optional[str]` | `category: String?` | `"category"` | PASS |
| `thumbnail_url: Optional[str]` | `thumbnailUrl: String?` | `"thumbnail_url"` | PASS |
| `banner_url: Optional[str]` | `bannerUrl: String?` | `"banner_url"` | PASS |
| `latest_video: Optional[LatestVideoResponse]` | `latestVideo: HomeChannelVideo?` | `"latest_video"` | PASS |

| Backend Field (LatestVideoResponse) | Frontend Field (HomeChannelVideo) | CodingKey | Result |
|------|------|------|------|
| `video_id: str` | `videoId: String` | `"video_id"` | PASS |
| `title: str` | `title: String` | `"title"` | PASS |
| `thumbnail_url: Optional[str]` | `thumbnailUrl: String?` | `"thumbnail_url"` | PASS |
| `duration: Optional[int]` | `duration: Int?` | `"duration"` | PASS |
| `published_at: Optional[int]` | `publishedAt: Int?` | `"published_at"` | PASS |

Response wrapper: backend `ChannelsHomeResponse.channels` matches frontend `HomeChannelsResponse.channels`. **PASS**

### 3. Error Handling
| Check | Result |
|-------|--------|
| Backend returns 404 for invalid child_id | PASS |
| Backend gracefully handles Invidious failures (logs warning, returns null metadata) | PASS |
| Frontend silently catches `loadHomeChannels` errors (non-critical) | PASS |
| Banner shows placeholder when no channels exist | PASS |
| Channel row hides itself when channels list is empty | PASS |

### 4. Data Layer
| Check | Result |
|-------|--------|
| `get_channels_with_latest_video()` filters by `status = 'allowed'` (excludes blocked) | PASS |
| SQL uses `ROW_NUMBER()` to pick most recent video per channel | PASS |
| Only approved videos included (`cva.status = 'approved'`); `request_video()` stores `'approved'` for auto-approved | PASS |
| Results ordered by `published_at DESC NULLS LAST` | PASS |
| Per-child isolation (child_id filter on both channels and video access) | PASS |
| LEFT JOIN ensures channels without videos still appear | PASS |

### 5. Invidious Client Enhancements
| Check | Result |
|-------|--------|
| `get_channel_info()` now returns `thumbnail_url` from `authorThumbnails` | PASS |
| `get_channel_info()` now returns `banner_url` from `authorBanners` | PASS |
| Protocol-relative URLs (`//`) are prefixed with `https:` | PASS |
| Relative URLs (`/`) are prefixed with Invidious base URL | PASS |
| Prefers 100-200px thumbnail and 1000-2000px banner widths | PASS |

### 6. Test Coverage
| Check | Result |
|-------|--------|
| Server: All 533 tests pass | PASS |
| tvOS: All 120 tests pass | PASS |
| New `TestChannelsWithLatestVideo` (7 tests): ordering, isolation, blocked exclusion, approved-only | PASS |
| New `TestChannelsHomeEndpoint` (5 tests): 404, empty, metadata, no-channel-id, Invidious failure | PASS |

### 7. Project Structure
| Check | Result |
|-------|--------|
| `project.yml` uses directory sources — new files auto-included | PASS |
| Xcode project (`project.pbxproj`) updated with new file references | PASS |

---

## Bugs Found

### BUG 1: Channel catalog filter sends `channelId` but backend expects `channelName` (CRITICAL)

**Location:** `tvos/Sources/Views/Home/HomeView.swift`
**Severity:** Critical — clicking a channel to filter the catalog will always return empty results.

**Details:**
When a user clicks a channel in the channel row, the frontend sets:
```swift
viewModel.selectedChannelFilter = channel.channelId  // e.g., "UCX6OQ..."
```
This value is passed to `getCatalog()` as the `channel` query parameter. But the backend catalog endpoint (`get_approved_videos()`) filters by channel *name*, not channel ID:
```python
if channel:
    where_parts.append("v.channel_name = ? COLLATE NOCASE")
    params.append(channel)
```

A `channelId` like `"UCX6OQ"` will never match a `channel_name` like `"CrashCourse"`, so the catalog will show 0 results.

**Fix options:**
- **(A) Frontend fix (simpler):** Change HomeView to pass `channel.channelName` instead of `channel.channelId`:
  ```swift
  viewModel.selectedChannelFilter = channel.channelName
  ```
- **(B) Backend fix:** Update `get_approved_videos()` to also match by `channel_id` or accept a separate `channel_id` query param.

---

### BUG 2: Channel filter pill label shows focused channel instead of selected channel (Minor)

**Location:** `tvos/Sources/Views/Home/HomeView.swift`, `channelFilterPill` view
**Severity:** Minor — UI cosmetic issue, does not affect functionality.

**Details:**
The channel filter pill displays:
```swift
Text("Channel: \(viewModel.focusedChannel?.channelName ?? "")")
```

But `focusedChannel` changes whenever the user moves focus in the channel row, while `selectedChannelFilter` is set when a channel is *clicked*. After clicking channel A and then moving focus to channel B, the pill would show "Channel: B" even though the catalog is filtering by channel A.

**Fix:** Look up the selected channel from `selectedChannelFilter`:
```swift
let selectedName = viewModel.homeChannels
    .first(where: { $0.channelId == viewModel.selectedChannelFilter })?.channelName ?? ""
Text("Channel: \(selectedName)")
```

---

## Bug Fix Verification (2026-03-23)

Both bugs were fixed by frontend-dev and re-verified by QA:

- **Bug 1 FIXED (frontend):** `HomeView.swift` line 94 now uses `channel.channelName` instead of `channel.channelId`. Catalog filter correctly matches the backend's `channel_name` field.
- **Bug 1 FIXED (backend, defense-in-depth):** `get_approved_videos()` in `video_store.py` now matches the `channel` param against both `v.channel_name` (case-insensitive) and `v.channel_id`. The catalog filter now works with either value.
- **Bug 2 FIXED:** `HomeView.swift` line 266 now uses `viewModel.selectedChannelFilter` directly instead of `viewModel.focusedChannel?.channelName`. Pill label correctly shows the selected channel.

**Re-verification results:** All 120 tvOS tests pass, all 534 server tests pass.

---

## Overall Assessment

The implementation is solid and well-structured. The new endpoint, models, and views are well-aligned. The backend test coverage is thorough with 12 new tests covering all critical paths.

**Status:** All bugs fixed and verified. Ready for merge.
