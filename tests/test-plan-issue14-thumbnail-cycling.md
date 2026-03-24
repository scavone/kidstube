# Test Plan — Issue #14: Thumbnail Preview Cycling

**Date:** 2026-03-24
**Feature:** Thumbnail preview cycling on video cards (Apple TV focus behavior)
**Status:** Phase 1 — Pre-implementation

---

## Overview

When a video card receives focus on tvOS, the card should cycle through multiple thumbnail images with a crossfade animation (like YouTube's native Apple TV app). The feature requires:

1. **Backend**: Expose an array of thumbnail URLs per video in API responses
2. **Frontend**: Timer-driven cycling logic with crossfade, fallback to single thumbnail, memory-conscious image management

---

## Backend Tests

### B1 — `_normalize_video` exposes multiple thumbnails

| # | Test | Expected |
|---|------|----------|
| B1.1 | `_normalize_video` returns a `thumbnail_urls` list when Invidious provides multiple `videoThumbnails` | List contains ≥1 URL, sorted by quality preference |
| B1.2 | Priority order: `maxres` > `high` > `medium` > `sddefault` > `default` > others | Highest-quality URLs appear first |
| B1.3 | Relative thumbnail URLs are made absolute (prepend `self.base_url`) | All URLs in `thumbnail_urls` start with `http` |
| B1.4 | `thumbnail_url` (single, legacy) still present and matches first entry in `thumbnail_urls` | Backward-compatible |
| B1.5 | When Invidious returns no `videoThumbnails`, `thumbnail_urls` is an empty list (not null) | `[]` not `null` |
| B1.6 | When only one thumbnail quality is available, list has one entry | `len == 1` |
| B1.7 | Deduplication: identical URLs are not repeated in the list | No duplicate entries |

### B2 — API endpoint responses include `thumbnail_urls`

| # | Test | Expected |
|---|------|----------|
| B2.1 | `GET /api/catalog` — each video dict in `videos` array has `thumbnail_urls` key | Present, type `list` |
| B2.2 | `GET /api/channels/home` — `LatestVideoResponse` includes `thumbnail_urls` | Present |
| B2.3 | `GET /api/recently-added` — each video dict has `thumbnail_urls` | Present |
| B2.4 | `GET /api/channel/{channel_id}` — video entries in `videos` array have `thumbnail_urls` | Present |
| B2.5 | `GET /api/search` — search results with type `video` include `thumbnail_urls` | Present |
| B2.6 | `thumbnail_urls` is always an array even when empty (never `null`) | `[]` not `null` |
| B2.7 | Short videos (<60s) with fewer thumbnails still return a valid (possibly 1-element) array | No crash |

### B3 — Pydantic model validation

| # | Test | Expected |
|---|------|----------|
| B3.1 | `VideoResponse` (or equivalent) serializes `thumbnail_urls` as a JSON array | `[]` by default, not omitted |
| B3.2 | `LatestVideoResponse` updated with `thumbnail_urls` field | Present in schema |

### B4 — Edge cases

| # | Test | Expected |
|---|------|----------|
| B4.1 | Video with malformed/missing `videoThumbnails` key does not raise exception | Returns `[]` |
| B4.2 | Thumbnail with `url: null` or empty string is skipped | Not included in list |
| B4.3 | Max list size is bounded (e.g. ≤ 5 URLs) to limit payload size | List does not exceed cap |

---

## Frontend (tvOS) Tests

### F1 — `ThumbnailCycler` or equivalent model unit tests

| # | Test | Expected |
|---|------|----------|
| F1.1 | Decode `Video` with `thumbnail_urls: ["url1","url2","url3"]` | `thumbnailUrls` array has 3 elements |
| F1.2 | Decode `Video` with `thumbnail_urls: []` | `thumbnailUrls` is empty array (not nil) |
| F1.3 | Decode `Video` with missing `thumbnail_urls` key (backward compat) | Decodes without error; `thumbnailUrls` is nil or `[]` |
| F1.4 | `Video.currentThumbnailUrl` (or equivalent computed property) returns `thumbnailUrl` when `thumbnailUrls` is empty | Falls back to `thumbnail_url` |
| F1.5 | `Video.currentThumbnailUrl` cycles index 0→1→2→0 when `thumbnailUrls` has 3 entries | Cycling wraps correctly |

### F2 — Cycling timer behavior (ViewModel/State tests)

| # | Test | Expected |
|---|------|----------|
| F2.1 | On focus gain, cycling timer starts and advances index | Index increments after interval |
| F2.2 | On focus loss, cycling timer stops and index resets to 0 | No further index increments after unfocus |
| F2.3 | When `thumbnailUrls` has only 1 entry, timer is not started (no-op cycling) | Timer not created |
| F2.4 | When `thumbnailUrls` is empty, timer is not started | Timer not created |
| F2.5 | Rapid focus/unfocus does not leave orphaned timers | At most one active timer per card |

### F3 — Model decoding

| # | Test | Expected |
|---|------|----------|
| F3.1 | `CatalogResponse` video dicts with `thumbnail_urls` decode into `Video` models correctly | No decode error |
| F3.2 | `LatestVideoResponse` / `HomeChannel` model includes `thumbnailUrls` field | Decoded from `thumbnail_urls` |
| F3.3 | `SearchResult` model includes `thumbnailUrls` field | Decoded from `thumbnail_urls` |
| F3.4 | Full round-trip: server JSON → `Video` → `thumbnailUrls[1]` is accessible | No data loss |

---

## Integration Contract Tests

### I1 — Field name alignment

| # | Check | Pass criteria |
|---|-------|---------------|
| I1.1 | Backend field name is `thumbnail_urls` (snake_case) | Matches Swift `CodingKey` `"thumbnail_urls"` |
| I1.2 | Backend type is `list[str]` (JSON array of strings) | Matches Swift `[String]` |
| I1.3 | Empty case: backend sends `[]`, Swift decodes as empty array | No null/missing mismatch |
| I1.4 | `thumbnail_url` (single, legacy) is still present alongside `thumbnail_urls` | No regression on existing thumbnail display |

### I2 — End-to-end flow

| # | Scenario | Expected |
|---|----------|----------|
| I2.1 | Catalog endpoint returns `thumbnail_urls` with ≥2 entries for a normal video | tvOS can cycle |
| I2.2 | Catalog endpoint returns `thumbnail_urls: []` for a video with no thumbnails | tvOS falls back to `thumbnail_url` |
| I2.3 | Server responds without `thumbnail_urls` field (pre-migration data) | tvOS decodes gracefully (field is Optional or has default `[]`) |

---

## Test Execution Plan

### Phase 2 Commands (after dev completion)

```bash
# Server tests
cd server && source .venv/bin/activate && python -m pytest

# tvOS model/unit tests
cd tvos && swift test

# tvOS full build verification
cd tvos && xcodegen generate && xcodebuild \
  -project KidsTube.xcodeproj \
  -scheme KidsTube \
  -destination "generic/platform=tvOS" \
  -configuration Release \
  CODE_SIGN_IDENTITY="-" \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGNING_ALLOWED=NO \
  ONLY_ACTIVE_ARCH=NO \
  build \
  CONFIGURATION_BUILD_DIR=/tmp/KidsTubeBuild
```

### Key integration checks at review time

1. Confirm `thumbnail_urls` key name matches exactly between backend `VideoResponse`/DB serializer and tvOS `CodingKeys`
2. Confirm `thumbnail_urls` is never serialized as `null` — always `[]` when empty
3. Confirm `thumbnail_url` (legacy single) is still returned for backward compatibility
4. Confirm tvOS cycling timer is invalidated on cell reuse/disappear (memory leak check)
5. Confirm no overlap between changed server files and changed tvOS files
