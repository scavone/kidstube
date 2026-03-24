# QA Report — Issue #14: Thumbnail Preview Cycling

**Date:** 2026-03-24
**Status: READY FOR MERGE**

---

## Test Results

| Suite | Result |
|-------|--------|
| `pytest` (full server suite) | **700/700 passed** |
| `swift test` (tvOS model/unit suite) | **126/126 passed** |
| `xcodebuild` (tvOS Release build) | **BUILD SUCCEEDED** |

---

## API Contract Review

### Field name and type alignment

| Check | Backend | Frontend | Result |
|-------|---------|----------|--------|
| Field name | `thumbnail_urls` (snake_case) | `case thumbnailUrls = "thumbnail_urls"` | ✅ Match |
| Type | `list[str]` with `default_factory=list` | `[String]?` | ✅ Safe (never `null` from server; `?? []` at all call sites) |
| Legacy `thumbnail_url` preserved | ✅ All responses | ✅ All models | ✅ No regression |
| Empty array when no extras | `[]` via `Field(default_factory=list)` | Swift ignores/handles | ✅ |

### Endpoint coverage

| Endpoint | Enrichment method | Covered by test | Result |
|----------|------------------|-----------------|--------|
| `GET /api/catalog` | `_add_thumbnail_urls()` | `TestCatalogThumbnailUrls` | ✅ |
| `GET /api/recently-added` | `_add_thumbnail_urls()` | `TestRecentlyAddedThumbnailUrls` | ✅ |
| `GET /api/video/{id}` | `_add_thumbnail_urls()` | `TestVideoDetailThumbnailUrls` | ✅ |
| `GET /api/channels-home` (latest_video) | `_add_thumbnail_urls()` | `TestChannelsHomeThumbnailUrls` | ✅ |
| `GET /api/channels/{id}` (detail videos) | `_add_thumbnail_urls()` | `TestChannelDetailThumbnailUrls` | ✅ |
| `GET /api/search` | `_normalize_video()` | `TestSearchThumbnailUrls` | ✅ |

### Swift call sites

All 6 `VideoCard(...)` call sites pass `thumbnailUrls: video.thumbnailUrls ?? []` — correctly unwrapping the Optional and falling back to an empty array. Confirmed in:
- `HomeView.swift` (2 sites)
- `CategoryContentView.swift`
- `ChannelDetailView.swift`
- `SearchResultsView.swift`
- `SidebarSearchView.swift`

---

## Code Review Findings

### Timer lifecycle — no leak

`FocusCycleModifier` correctly:
- Cancels any prior task before starting a new one (`cycleTask?.cancel()` at the top of `startCycling()`)
- Cancels on focus loss (`onChange(of: isFocused)` → else branch)
- Cancels on `onDisappear`
- Only starts if `!thumbnailUrls.isEmpty` (prevents no-op timer for single-thumbnail cards)

### Index safety

`let idx = min(currentThumbIndex, thumbnailUrls.count - 1)` guards against out-of-bounds if the array size changes mid-cycle. ✅

### File conflict check

No files appear in both teammate change sets:
- Backend: `server/invidious/client.py`, `server/api/models.py`, `server/api/routes.py`, `server/tests/test_invidious_client.py`, `server/tests/test_thumbnail_urls.py`
- Frontend: `tvos/Sources/Models/Video.swift`, `SearchResult.swift`, `HomeChannel.swift`, `tvos/Sources/Views/Components/VideoCard.swift`, `HomeView.swift`, `CategoryContentView.swift`, `ChannelDetailView.swift`, `SearchResultsView.swift`, `SidebarSearchView.swift`

No overlap. ✅

---

## Non-blocking Observations

1. **`ChannelHomeItem.thumbnail_urls` is unused**: The Python `ChannelHomeItem` model has `thumbnail_urls: list[str]` at the *channel* level (not the latest_video level). This always serializes as `[]` since it's never populated. Swift's `HomeChannel` has no matching property and silently ignores the field. No crash, no regression — just a vestigial field. Not blocking.

2. **Thumbnail URLs are public YouTube CDN** (`https://i.ytimg.com/vi/{id}/1.jpg`), not Invidious-proxied. This is consistent with how the existing `thumbnail_url` field works today. Design decision, not a bug.

---

## Conclusion

**Ready for merge.** All 826 tests pass, tvOS release build succeeds, API contract is correctly aligned between backend and frontend, timer lifecycle is clean with no leak vectors, and there are no file conflicts between teammates.
