# BrainRotGuard for Apple TV — Development Plan

> **Purpose:** This document is a complete implementation plan for Claude Code (or any developer). It describes a YouTube parental control system that runs on Apple TV, with a self-hosted backend, Telegram parent controls, Invidious-powered video streaming, and multi-child profile support.

---

## 1. Project Overview

### What We're Building

A parental YouTube control system with three components:

1. **Server (Python/FastAPI)** — Self-hosted backend that manages video approvals, child profiles, watch time tracking, and communicates with Invidious for video search/streaming. Heavily inspired by [BrainRotGuard](https://github.com/GHJJ123/brainrotguard) but rebuilt to support multi-child profiles and Invidious as the video backend.

2. **Telegram Bot** — Parent-facing interface for approving/denying video requests, managing channels, setting per-child time limits, and viewing activity. Runs as part of the server process.

3. **tvOS App (Swift/SwiftUI)** — A native Apple TV app that children use to search for and watch approved YouTube videos. Uses AVPlayer with stream URLs provided by the server (sourced from Invidious). Supports multiple child profiles with a profile picker at launch.

### Key Architectural Decision: Invidious

Instead of embedding YouTube iframes (which don't work on tvOS) or fighting yt-dlp stream extraction, we use a **self-hosted Invidious instance** as the video backend. Invidious:
- Provides a REST API for search, metadata, and channel listings
- Proxies YouTube video streams through the server, returning direct URLs playable by AVPlayer
- Eliminates the need for YouTube API keys
- Is maintained by an active open-source community

The server talks to Invidious's API. The tvOS app talks to the server. The parent talks to the Telegram bot. The child never touches YouTube directly.

### Sideloading Strategy: atvloadly

Since Apple TV 4K has no USB port, traditional sideloading tools like AltStore or Sideloadly have limited tvOS support. The recommended approach is **[atvloadly](https://github.com/bitxeno/atvloadly)** — a Dockerized web service that:
- Pairs with Apple TV over Wi-Fi (no USB needed)
- Sideloads IPA files via a web UI
- **Automatically refreshes the app** before the 7-day free signing expiration
- Runs on the same Linux server as the rest of the stack

This means the entire system (Invidious, BrainRotGuard server, atvloadly) can run as a single Docker Compose stack, and the tvOS app stays permanently installed without manual re-signing.

**Requirements:**
- A dedicated/burner Apple ID (free account is fine, 3 active apps max)
- Apple TV must be on the same network as the server
- Initial pairing done through Apple TV Settings → Remote and Devices → Remote App and Devices

---

## 2. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Home Server (Docker Compose)                  │
│                                                                      │
│  ┌─────────────┐   ┌──────────────────┐   ┌──────────────────────┐  │
│  │  Invidious   │   │  BrainRotGuard   │   │     atvloadly        │  │
│  │  + Companion │◄──│  Server (FastAPI) │   │  (sideload manager)  │  │
│  │  + PostgreSQL│   │  + Telegram Bot   │   │                      │  │
│  │  :3000       │   │  :8080            │   │  :5533               │  │
│  └─────────────┘   └────────┬─────────┘   └──────────────────────┘  │
│                              │                        │              │
└──────────────────────────────┼────────────────────────┼──────────────┘
                               │                        │
                    ┌──────────▼──────────┐   ┌────────▼────────┐
                    │   Apple TV (tvOS)    │   │  Telegram Cloud  │
                    │   Native SwiftUI    │   │                  │
                    │   app — AVPlayer    │   │  ┌────────────┐  │
                    │   streams video     │   │  │ Parent's    │  │
                    │   from server       │   │  │ Phone       │  │
                    └─────────────────────┘   │  └────────────┘  │
                                              └─────────────────┘
```

### Data Flow

1. **Child selects profile** on Apple TV → app loads that child's catalog and limits from server
2. **Child searches** → tvOS app calls `GET /api/search?q=...&child_id=X` → server queries Invidious API → returns filtered results
3. **Child requests video** → `POST /api/request` → server checks channel allow/block lists → if not pre-approved, sends Telegram notification to parent
4. **Parent approves** via Telegram → server updates DB status
5. **tvOS app polls** `GET /api/status/{video_id}` → detects approval → calls `GET /api/stream/{video_id}` → server fetches proxied stream URL from Invidious → returns URL to tvOS app
6. **AVPlayer plays** the stream URL → tvOS app sends heartbeats to `POST /api/watch-heartbeat` to track watch time
7. **Server enforces** daily time limits, schedule windows, and category budgets per child

---

## 3. Component Specifications

### 3.1 Invidious Instance (Existing Software — Deploy Only)

**No code to write.** Deploy the official Invidious Docker image with Invidious Companion.

**Relevant API endpoints we'll consume:**

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/search?q=` | Search YouTube videos |
| `GET /api/v1/videos/:id` | Video metadata + `formatStreams[]` with direct URLs |
| `GET /api/v1/channels/:id` | Channel info |
| `GET /api/v1/channels/:id/videos` | Channel video listing |

**Critical config:**
- `local: true` in Invidious config (proxy video streams through Invidious so the Apple TV never contacts Google directly)
- Invidious Companion enabled for reliable stream resolution
- Not exposed to the internet — only accessible on the local Docker network

**Docker service definition (reference):**
```yaml
invidious:
  image: quay.io/invidious/invidious:latest
  environment:
    INVIDIOUS_CONFIG: |
      db:
        dbname: invidious
        user: kemal
        password: kemal
        host: invidious-db
        port: 5432
      check_tables: true
      local: true
      external_port: 3000
      domain: localhost
      https_only: false
      invidious_companion:
        - private_url: http://companion:8282
  depends_on:
    - invidious-db
    - companion

invidious-db:
  image: docker.io/library/postgres:14
  environment:
    POSTGRES_DB: invidious
    POSTGRES_USER: kemal
    POSTGRES_PASSWORD: kemal
  volumes:
    - invidious-db:/var/lib/postgresql/data

companion:
  image: quay.io/invidious/invidious-companion:latest
  environment:
    - SERVER_SECRET_KEY=CHANGE_ME
```

### 3.2 BrainRotGuard Server (Python/FastAPI) — Rebuild

Rebuild the server from BrainRotGuard's architecture, with these changes:

#### 3.2.1 What to Reuse from BrainRotGuard

The original codebase at https://github.com/GHJJ123/brainrotguard is well-structured. Reuse the **patterns and logic** from:

- `config.py` — Config loading from YAML + env vars with `${VAR}` expansion (reuse as-is or near-identical)
- `utils.py` — Time utilities: `get_today_str()`, `get_day_utc_bounds()`, `parse_time_input()`, `is_within_schedule()`, `format_time_12h()` (reuse as-is)
- `data/video_store.py` — SQLite data layer patterns: WAL mode, thread lock, schema migration with `_add_column_if_missing()`, settings key-value store, watch_log tracking, channel allow/block lists, word filters (reuse patterns, extend schema)
- `bot/telegram_bot.py` — Telegram approval flow: notification with thumbnail + inline buttons, callback handling for approve/deny/allow-channel/block-channel, command handlers for `/pending`, `/approved`, `/stats`, `/channel`, `/time`, `/watch`, `/search` (reuse patterns, extend for multi-child)
- `web/app.py` — Rate limiting with slowapi, CSRF protection, heartbeat dedup logic, time limit checking, schedule window checking, catalog building with channel cache (reuse patterns, replace web UI routes with API-only endpoints)
- `main.py` — Orchestrator pattern: async startup of FastAPI + Telegram bot, signal handling, background tasks (reuse pattern)

#### 3.2.2 What to Change

**Replace yt-dlp with Invidious API calls:**

Create `invidious/client.py` — an async HTTP client (httpx) that wraps the Invidious API:

```python
class InvidiousClient:
    def __init__(self, base_url: str = "http://invidious:3000"):
        self.base_url = base_url

    async def search(self, query: str, max_results: int = 20) -> list[dict]:
        """GET /api/v1/search?q={query}&type=video"""

    async def get_video(self, video_id: str) -> dict | None:
        """GET /api/v1/videos/{video_id}
        Returns metadata + formatStreams with direct playable URLs"""

    async def get_stream_url(self, video_id: str, quality: str = "best") -> str | None:
        """Extract best stream URL from formatStreams for AVPlayer.
        Prefer: 720p or 1080p, mp4 container, progressive stream.
        Returns the proxied Invidious URL (goes through local Invidious)."""

    async def get_channel_videos(self, channel_id: str, continuation: str = "") -> list[dict]:
        """GET /api/v1/channels/{channel_id}/videos"""

    async def get_channel_info(self, channel_id: str) -> dict | None:
        """GET /api/v1/channels/{channel_id}"""
```

**Replace HTML web routes with JSON API endpoints** (the tvOS app is the only client):

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/profiles` | GET | List all child profiles |
| `/api/profiles` | POST | Create child profile (parent-only, via Telegram or setup) |
| `/api/search` | GET | Search videos (params: `q`, `child_id`) |
| `/api/request` | POST | Request video approval (params: `video_id`, `child_id`) |
| `/api/status/{video_id}` | GET | Poll approval status |
| `/api/stream/{video_id}` | GET | Get playable stream URL for approved video |
| `/api/catalog` | GET | Paginated approved video library (params: `child_id`, `category`, `channel`, `offset`, `limit`) |
| `/api/channels` | GET | List allowed channels with their categories |
| `/api/watch-heartbeat` | POST | Report playback seconds (params: `video_id`, `child_id`, `seconds`) |
| `/api/time-status` | GET | Get remaining time budget for child (params: `child_id`) |
| `/api/schedule-status` | GET | Check if current time is within allowed schedule (params: `child_id`) |

**Add multi-child profile support to the data layer:**

Extend the SQLite schema:

```sql
CREATE TABLE children (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    avatar TEXT,  -- emoji or color identifier for the tvOS profile picker
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Per-child settings (daily limits, schedule, categories)
CREATE TABLE child_settings (
    child_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (child_id, key),
    FOREIGN KEY (child_id) REFERENCES children(id)
);

-- Track which child requested/watches each video
ALTER TABLE watch_log ADD COLUMN child_id INTEGER REFERENCES children(id);

-- Per-child video approvals (a video approved for one child may not be for another)
CREATE TABLE child_video_access (
    child_id INTEGER NOT NULL,
    video_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/approved/denied
    requested_at TEXT NOT NULL DEFAULT (datetime('now')),
    decided_at TEXT,
    PRIMARY KEY (child_id, video_id),
    FOREIGN KEY (child_id) REFERENCES children(id)
);
```

**Key design decisions for multi-child:**
- Channel allow/block lists are **global** (shared across children) — if a channel is trusted, it's trusted for all kids. This keeps management simple.
- **Video approval is per-child.** A video approved for the 12-year-old isn't auto-approved for the 7-year-old. When parent approves, Telegram shows which child requested it.
- **Time limits, schedule windows, and category budgets are per-child** (stored in `child_settings`).
- The Telegram notification includes the child's name: "**[Alex] New Video Request**"
- Telegram commands accept an optional child name: `/time Alex set 90`, `/watch Alex`, `/stats Alex`

**Extend Telegram bot for multi-child:**

- Approval notification now shows: `[ChildName] New Video Request`
- Inline buttons include child context in callback data: `approve_edu:childId:videoId`
- New commands:
  - `/kids` — List all child profiles with their current status (time used, videos pending)
  - `/addkid Name` — Create a new child profile
  - `/time ChildName set 90` — Set daily limit for specific child
  - `/time ChildName schedule 800 2000` — Set schedule for specific child
  - `/watch ChildName` — View watch activity for specific child
  - `/stats ChildName` — View stats for specific child
- If only one child exists, child name can be omitted from commands (backward compatible)

#### 3.2.3 Server API Authentication

The tvOS app authenticates to the server with a simple shared secret (API key) passed in the `Authorization` header. This is sufficient for a LAN-only service. The key is configured in the server's `.env` file and hardcoded into the tvOS app at build time.

```
Authorization: Bearer {BRG_API_KEY}
```

All `/api/*` endpoints require this header. The server validates it with constant-time comparison.

### 3.3 tvOS App (Swift/SwiftUI) — New Build

#### 3.3.1 Tech Stack

- **Swift 5.9+** / **SwiftUI** (tvOS 17.0+ minimum deployment target)
- **AVKit / AVPlayer** for video playback (native HLS and progressive stream support)
- **URLSession** for networking (no third-party dependencies to keep sideloading simple)
- **No external dependencies** — minimizes build complexity and IPA size

#### 3.3.2 App Structure

```
BrainRotGuardTV/
├── BrainRotGuardTVApp.swift          # App entry point
├── Config.swift                       # Server URL, API key constants
├── Models/
│   ├── ChildProfile.swift             # Child profile model
│   ├── Video.swift                    # Video metadata model
│   ├── SearchResult.swift             # Search result model
│   └── TimeStatus.swift               # Time budget model
├── Services/
│   ├── APIClient.swift                # HTTP client for server API
│   └── HeartbeatService.swift         # Background timer for watch heartbeats
├── Views/
│   ├── ProfilePicker/
│   │   └── ProfilePickerView.swift    # Launch screen: "Who's watching?"
│   ├── Home/
│   │   ├── HomeView.swift             # Main screen: search bar + catalog grid
│   │   ├── CatalogGridView.swift      # Scrollable grid of video thumbnails
│   │   └── CategoryFilterView.swift   # Edu / Fun / All filter tabs
│   ├── Search/
│   │   └── SearchResultsView.swift    # Search results with Request buttons
│   ├── Player/
│   │   ├── PlayerView.swift           # Full-screen AVPlayer wrapper
│   │   └── PlayerOverlayView.swift    # Time remaining overlay
│   ├── Pending/
│   │   └── PendingView.swift          # "Waiting for approval" polling screen
│   ├── Denied/
│   │   └── DeniedView.swift           # "Video not approved" screen
│   ├── TimesUp/
│   │   └── TimesUpView.swift          # "Time limit reached" screen
│   └── Components/
│       ├── VideoCard.swift            # Thumbnail + title + duration card
│       └── TimeBadge.swift            # Remaining time indicator
└── Assets.xcassets                    # App icon, colors, images
```

#### 3.3.3 Screen Flow

```
┌─────────────────┐
│  Profile Picker  │──► Select child ──┐
│  "Who's watching?"│                   │
└─────────────────┘                    ▼
                              ┌─────────────────┐
                              │    Home Screen    │
                              │ Search | Catalog  │
                              │ [Edu] [Fun] [All] │
                              └───────┬───────────┘
                                      │
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                   ▼
           ┌──────────────┐ ┌──────────────┐   ┌──────────────┐
           │ Search Results│ │ Video Detail  │   │ Channel View  │
           │ [Request]     │ │ [Watch]       │   │ (filtered)    │
           └──────┬───────┘ └──────┬───────┘   └──────────────┘
                  │                │
                  ▼                ▼
           ┌──────────────┐ ┌──────────────┐
           │ Pending       │ │ Player        │
           │ (polling)     │ │ (AVPlayer)    │
           └──────┬───────┘ │ + heartbeat   │
                  │         │ + time overlay │
         ┌────────┼────────┐└──────────────┘
         ▼        ▼        ▼
    [Approved] [Denied] [TimesUp]
    → Player   → Back   → Back
```

#### 3.3.4 Key Implementation Details

**Profile Picker:**
- Grid of child profiles fetched from `GET /api/profiles`
- Each profile shows name + avatar (emoji)
- Selected profile stored in app state for the session
- Focus-based navigation with Siri Remote

**Home Screen:**
- Top: Search bar (tvOS keyboard input)
- Below: Category filter tabs (All / Educational / Entertainment)
- Below: Scrollable grid of video cards loaded from `GET /api/catalog`
- Infinite scroll pagination
- Time remaining badge in the top-right corner (fetched from `GET /api/time-status`)

**Search:**
- User types query → `GET /api/search?q=...&child_id=X`
- Results displayed as video cards with "Request" button
- If video is already approved, show "Watch" button instead

**Request & Approval Polling:**
- `POST /api/request` with `video_id` and `child_id`
- Navigate to PendingView
- Poll `GET /api/status/{video_id}?child_id=X` every 3 seconds
- On "approved" → navigate to PlayerView
- On "denied" → show DeniedView

**Video Player:**
- Fetch stream URL: `GET /api/stream/{video_id}` → returns `{ "url": "http://invidious:3000/..." }`
- Create `AVPlayer(url:)` with the stream URL
- Use `AVPlayerViewController` wrapped for SwiftUI (gives native tvOS playback controls for free — play/pause/scrub with Siri Remote)
- Start `HeartbeatService`: Timer fires every 30 seconds, sends `POST /api/watch-heartbeat` with `{ video_id, child_id, seconds: 30 }`
- Display time-remaining overlay (semi-transparent badge, auto-hides after 5 seconds, reappears on Siri Remote tap)
- If heartbeat response indicates time exceeded → pause player, navigate to TimesUpView
- If heartbeat response indicates outside schedule → pause player, navigate to OutsideHoursView

**tvOS Remote Navigation:**
- All navigation is focus-based (SwiftUI handles this naturally)
- Siri Remote clickpad for selection, Menu button for back
- Player uses native AVPlayerViewController controls (no custom transport needed)

#### 3.3.5 Build & Sideload

The tvOS app should be built as a standard Xcode project:
- Target: tvOS 17.0+
- No entitlements requiring paid developer account (no CloudKit, no push notifications)
- Archive → Export as IPA
- Upload IPA to atvloadly web UI → install on Apple TV

Include a `Config.swift` with build-time constants:
```swift
enum Config {
    static let serverBaseURL = "http://192.168.1.X:8080"
    static let apiKey = "your-secret-key-here"
}
```

User will need to update these values before building.

---

## 4. Docker Compose (Full Stack)

The entire server-side stack in a single `docker-compose.yml`:

```yaml
services:
  # === Invidious (YouTube proxy + API) ===
  invidious:
    image: quay.io/invidious/invidious:latest
    restart: unless-stopped
    environment:
      INVIDIOUS_CONFIG: |
        db:
          dbname: invidious
          user: kemal
          password: ${INVIDIOUS_DB_PASSWORD:-kemal}
          host: invidious-db
          port: 5432
        check_tables: true
        local: true
        external_port: 3000
        domain: localhost
        https_only: false
        invidious_companion:
          - private_url: http://companion:8282
    ports:
      - "3000:3000"
    depends_on:
      - invidious-db
      - companion
    networks:
      - brg

  invidious-db:
    image: docker.io/library/postgres:14
    restart: unless-stopped
    environment:
      POSTGRES_DB: invidious
      POSTGRES_USER: kemal
      POSTGRES_PASSWORD: ${INVIDIOUS_DB_PASSWORD:-kemal}
    volumes:
      - invidious-db:/var/lib/postgresql/data
    networks:
      - brg

  companion:
    image: quay.io/invidious/invidious-companion:latest
    restart: unless-stopped
    environment:
      - SERVER_SECRET_KEY=${INVIDIOUS_COMPANION_SECRET:-change_me_companion}
    networks:
      - brg

  # === BrainRotGuard Server ===
  brainrotguard:
    build: ./server
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - BRG_BOT_TOKEN=${BRG_BOT_TOKEN}
      - BRG_ADMIN_CHAT_ID=${BRG_ADMIN_CHAT_ID}
      - BRG_API_KEY=${BRG_API_KEY}
      - BRG_INVIDIOUS_URL=http://invidious:3000
      - BRG_TIMEZONE=${BRG_TIMEZONE:-America/New_York}
    volumes:
      - brg-db:/app/db
    depends_on:
      - invidious
    networks:
      - brg

  # === atvloadly (Apple TV sideloader) ===
  atvloadly:
    image: ghcr.io/bitxeno/atvloadly:latest
    privileged: true
    restart: unless-stopped
    ports:
      - "5533:80"
    volumes:
      - atvloadly-data:/data
      - /var/run/dbus:/var/run/dbus
      - /var/run/avahi-daemon:/var/run/avahi-daemon
    networks:
      - brg

volumes:
  invidious-db:
  brg-db:
  atvloadly-data:

networks:
  brg:
    driver: bridge
```

---

## 5. Implementation Order

Build in this order. Each phase produces a testable, working increment.

### Phase 1: Infrastructure (Day 1) -- COMPLETE

1. ~~Create project directory structure~~
2. ~~Write `docker-compose.yml` with Invidious + PostgreSQL + Companion~~
3. ~~Write `.env.example` with all required variables~~
4. Boot Invidious and verify it works: `curl http://localhost:3000/api/v1/search?q=test` *(deploy-time)*
5. Verify video stream proxying: fetch a video's `formatStreams` URL and confirm it's playable *(deploy-time)*

**49 tests passing. Committed.**

### Phase 2: Server Core (Days 2–4) -- COMPLETE

1. ~~Set up the FastAPI project in `server/`~~
2. ~~Port `config.py` and `utils.py` from BrainRotGuard (adapted for Invidious + multi-child)~~
3. ~~Build `invidious/client.py` with search, metadata, stream URL extraction~~
4. ~~Build `data/video_store.py` with extended schema (children, child_settings, child_video_access)~~
5. ~~Implement core API endpoints: `/api/profiles`, `/api/search`, `/api/request`, `/api/status`, `/api/stream`, `/api/catalog`, `/api/channels`, `/api/watch-heartbeat`, `/api/time-status`, `/api/schedule-status`~~
6. ~~Add API key authentication middleware~~
7. ~~Test all endpoints with pytest~~

**187 tests passing across config, utils, Invidious client, video store, auth, and full API integration. Committed.**

### Phase 3: Telegram Bot (Days 5–6) -- COMPLETE

1. ~~Port the Telegram bot from BrainRotGuard, adapting for multi-child~~
2. ~~Implement approval notification with child name + inline buttons~~
3. ~~Implement callback handling with child context in callback data~~
4. ~~Port commands: `/help`, `/pending`, `/approved`, `/stats`, `/channel`, `/time`, `/watch`, `/search`~~
5. ~~Add new commands: `/kids`, `/addkid`~~
6. ~~Wire up bot ↔ server communication (shared VideoStore instance)~~
7. ~~Test full approval flow: request via API → Telegram notification → approve → status poll shows approved~~

**268 tests passing (81 new bot tests). Committed.**

### Phase 4: tvOS App (Days 7–10) -- COMPLETE

1. ~~Create Xcode project targeting tvOS 17.0+~~
2. ~~Build `APIClient.swift` — URLSession wrapper for all server endpoints~~
3. ~~Build `ProfilePickerView` — "Who's watching?" grid~~
4. ~~Build `HomeView` with search bar, category filters, and catalog grid~~
5. ~~Build `SearchResultsView` with Request/Watch buttons~~
6. ~~Build `PendingView` with polling~~
7. ~~Build `PlayerView` — AVPlayerViewController wrapper with heartbeat timer~~
8. ~~Build time-remaining overlay and TimesUpView~~
9. ~~Polish focus navigation and Siri Remote interactions~~
10. Archive as IPA *(requires Xcode with tvOS SDK — project is build-ready)*

**68 tests passing (models, APIClient with mocks, config validation). Committed.**

### Phase 4.5: Child Profile Management -- COMPLETE

1. ~~Data layer: `update_child()` method, avatar file storage/retrieval on disk~~
2. ~~API: `PUT /api/profiles/{id}` (update name/avatar), `DELETE /api/profiles/{id}`, `POST /api/profiles/{id}/avatar` (upload photo), `GET /api/profiles/{id}/avatar` (serve photo, public — no auth required)~~
3. ~~Telegram bot: `/editkid` (rename, change avatar), `/removekid` (delete child + cascade), photo message handler (send photo with caption "avatar ChildName")~~
4. ~~tvOS: `ProfileCardView` supports photo avatars via `AsyncImage`, `ChildProfile` model has `hasPhotoAvatar` and `avatarURL` computed properties~~
5. ~~Server dependency: added `python-multipart` for file uploads~~
6. ~~Tests: 307 server tests passing, 68 tvOS tests passing~~

**Committed.**

### Phase 5: Sideloading & Integration (Day 11)

1. Add atvloadly to Docker Compose
2. Install `avahi-daemon` on the host Linux server
3. Boot atvloadly, log in with burner Apple ID
4. Pair with Apple TV
5. Upload the IPA and install
6. End-to-end test: profile select → search → request → parent approves → video plays → time tracking works
7. Verify auto-refresh keeps the app installed past 7 days

### Phase 6: Hardening (Day 12+)

1. DNS blocking setup documentation (same domains as original BrainRotGuard)
2. Add rate limiting to all API endpoints
3. Add input validation and error handling throughout
4. Add channel cache background refresh (port from BrainRotGuard's `_channel_cache_loop`)
5. Add word filter support
6. Write setup documentation / README

---

## 6. File Structure (Server)

```
server/
├── main.py                    # Orchestrator: runs FastAPI + Telegram bot
├── config.py                  # Config from YAML + env vars (port from BRG)
├── utils.py                   # Time utilities (port from BRG)
├── requirements.txt
├── Dockerfile
├── invidious/
│   ├── __init__.py
│   └── client.py              # Async Invidious API client
├── data/
│   ├── __init__.py
│   └── video_store.py         # SQLite data layer (extended from BRG)
├── bot/
│   ├── __init__.py
│   └── telegram_bot.py        # Telegram bot (extended from BRG)
└── api/
    ├── __init__.py
    ├── routes.py               # FastAPI route definitions
    ├── auth.py                 # API key middleware
    └── models.py               # Pydantic request/response models
```

---

## 7. Environment Variables

```bash
# === Telegram ===
BRG_BOT_TOKEN=123456789:ABCdefGhIjKlMnOpQrStUvWxYz
BRG_ADMIN_CHAT_ID=987654321

# === Server ===
BRG_API_KEY=generate-a-strong-random-key-here
BRG_TIMEZONE=America/New_York
BRG_WEB_PORT=8080

# === Invidious ===
INVIDIOUS_DB_PASSWORD=kemal
INVIDIOUS_COMPANION_SECRET=change_me_companion

# === Default Watch Limits (can be overridden per-child via Telegram) ===
BRG_DAILY_LIMIT_MINUTES=120
```

---

## 8. Critical Notes for Implementation

1. **Invidious stream URLs expire.** The server's `/api/stream/{video_id}` endpoint should fetch a fresh stream URL from Invidious on each request rather than caching them. They typically expire within a few hours.

2. **AVPlayer on tvOS natively supports both progressive MP4 and HLS.** Prefer progressive MP4 streams from Invidious's `formatStreams` array (not `adaptiveFormats` which require DASH, which AVPlayer doesn't support natively). Filter for `type` containing `video/mp4` and pick the highest quality ≤ 1080p.

3. **The tvOS app has no web views.** Everything is native SwiftUI. No HTML, no JavaScript, no iframes.

4. **atvloadly requires `avahi-daemon` on the Linux host** for mDNS/Bonjour discovery of the Apple TV. Install it: `sudo apt install avahi-daemon` (Debian/Ubuntu) or equivalent.

5. **Free Apple ID limit: 3 active apps.** The tvOS app will be one of those three. If you're sideloading other apps, plan accordingly.

6. **Invidious occasionally breaks** when YouTube changes their frontend. Monitor the Invidious GitHub for updates and `docker compose pull` to update. This is the one ongoing maintenance item.

7. **The original BrainRotGuard's web UI (`web/` directory, HTML templates, CSS) is NOT needed.** The tvOS app replaces it entirely. Don't port the templates or static files.

8. **Keep the server API stateless per-request.** The tvOS app should be the source of truth for "which child is using it" and pass `child_id` on every request.

---

## 9. Testing Checklist

- [ ] Invidious search returns results via API
- [ ] Invidious video stream URL is playable in a browser/VLC
- [ ] Server search endpoint filters blocked channels and word filters
- [ ] Server request endpoint sends Telegram notification with child name
- [ ] Telegram approve button updates video status in DB
- [ ] Server stream endpoint returns fresh, playable URL
- [ ] tvOS profile picker loads and selects profiles
- [ ] tvOS search displays results with thumbnails
- [ ] tvOS request → pending → approved flow works end-to-end
- [ ] AVPlayer plays video from Invidious stream URL
- [ ] Heartbeat tracking accumulates watch minutes correctly
- [ ] Time limit enforcement pauses playback when exceeded
- [ ] Schedule window blocks playback outside allowed hours
- [ ] Per-child time limits are independent
- [ ] Channel allow-list auto-approves for all children
- [ ] atvloadly installs IPA on Apple TV
- [ ] App survives 7-day auto-refresh cycle
