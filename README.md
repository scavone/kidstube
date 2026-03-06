# KidsTube

A parental YouTube control system for Apple TV. Children watch videos through a native tvOS app, while parents manage approvals, channels, and screen time limits through a Telegram bot.

Built on [Invidious](https://github.com/iv-org/invidious) to proxy YouTube without API keys or direct Google contact from the TV.

## How It Works

```
                        ┌─────────────────────────────┐
                        │         Home Server         │
                        │                             │
  ┌───────────┐         │  ┌──────────┐  ┌──────────┐ │
  │ Apple TV  │◄────────┼──│ KidsTube │──│Invidious │ │
  │ (tvOS app)│────────►│  │  Server  │  │ (YouTube │ │
  └───────────┘  :8080  │  │ (FastAPI)│  │  proxy)  │ │
                        │  └────┬─────┘  └──────────┘ │
                        └───────┼─────────────────────┘
                                │
                        ┌───────▼─────────┐
                        │  Telegram Bot   │
                        │ (parent's phone)│
                        └─────────────────┘
```

1. **Child picks their profile** on the Apple TV and browses/searches videos
2. **Server checks** channel allow/block lists and word filters per child
3. **Unapproved videos** trigger a Telegram notification to the parent
4. **Parent approves or denies** via inline buttons in Telegram
5. **Child watches** through the native AVPlayer; server tracks watch time
6. **Daily limits and schedule windows** are enforced per child

## Components

### Server (Python/FastAPI)

The backend in [server/](server/) handles everything: JSON API for the tvOS app, Telegram bot for parent controls, SQLite database, and Invidious integration.

Key features:
- Multi-child profiles with independent settings
- Per-child channel allow/block lists
- Video approval workflow (manual or auto-approve from allowed channels)
- Watch time tracking with daily limits and schedule windows
- HLS streaming via ffmpeg for adaptive quality
- Curated starter channels for onboarding
- Background channel refresh

### tvOS App (Swift/SwiftUI)

The native Apple TV app in [tvos/](tvos/) is what children interact with. Built with SwiftUI targeting tvOS 17.0+ with zero external dependencies.

Screens: Profile Picker, Home (search + catalog grid), Search Results, Pending Approval, Video Player (AVPlayer with heartbeat tracking), Time's Up, Denied.

### Invidious

A self-hosted [Invidious](https://github.com/iv-org/invidious) instance with [Invidious Companion](https://github.com/iv-org/invidious-companion) proxies all YouTube traffic. The Apple TV never contacts Google directly.

Critical config:
- `local: true` (proxy streams through Invidious)
- Companion enabled for reliable stream resolution
- Not exposed to the internet; only the KidsTube server talks to it

## Prerequisites

| Component | Purpose |
|---|---|
| **Python 3.12+** | Server runtime (or use the Docker image) |
| **Invidious + Companion + PostgreSQL** | YouTube proxy and stream resolution |
| **ffmpeg** | Server-side HLS muxing for adaptive streams |
| **Telegram Bot Token** | Create one via [@BotFather](https://t.me/BotFather) |
| **Xcode with tvOS SDK** | Building the Apple TV app |
| **Apple TV 4K** (tvOS 17+) | Running the app |
| **Sideloading tool** | e.g. [atvloadly](https://github.com/bitxeno/atvloadly) for wireless sideloading |

## Server Setup

### Configuration

Copy the example env file and fill in your values:

```bash
cd server
cp .env.example .env
```

Required variables:

| Variable | Description |
|---|---|
| `BRG_BOT_TOKEN` | Telegram bot token from @BotFather |
| `BRG_ADMIN_CHAT_ID` | Your Telegram user/chat ID (the parent) |
| `BRG_API_KEY` | Shared secret between server and tvOS app |

Optional variables:

| Variable | Default | Description |
|---|---|---|
| `BRG_APP_NAME` | `KidsTube` | Display name in Telegram messages |
| `BRG_BASE_URL` | *(auto-detect)* | External URL if behind a reverse proxy |
| `BRG_INVIDIOUS_URL` | `http://invidious:3000` | Invidious instance URL |
| `BRG_TIMEZONE` | `America/New_York` | Timezone for schedule/limits |
| `BRG_WEB_PORT` | `8080` | Server listen port |
| `BRG_DAILY_LIMIT_MINUTES` | `120` | Default daily screen time per child |
| `BRG_PREFERRED_AUDIO_LANG` | *(none)* | ISO 639-1 code (e.g. `en`) for multi-language videos |

### Running with Docker

A container image is built automatically on push to `main` and published to GHCR:

```
ghcr.io/<owner>/yt4kids/server:latest
```

Run it however you run containers (Docker, Podman, Kubernetes, etc.). The server needs:
- Port 8080 exposed
- A persistent volume mounted at `/app/db` for the SQLite database
- Network access to your Invidious instance
- The environment variables above

### Running directly

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Requires `ffmpeg` installed on the system for HLS streaming.

### Invidious Setup

Refer to the [Invidious installation docs](https://docs.invidious.io/installation/). You need:

1. **Invidious** with `local: true` and Companion configured
2. **Invidious Companion** for stream resolution
3. **PostgreSQL** for Invidious's database

Example Invidious config snippet:

```yaml
db:
  dbname: invidious
  user: kemal
  password: <password>
  host: <postgres-host>
  port: 5432
check_tables: true
local: true
external_port: 3000
domain: localhost
https_only: false
invidious_companion:
  - private_url: http://<companion-host>:8282
```

Keep Invidious on an internal network; only the KidsTube server needs to reach it.

## tvOS App Setup

### Build configuration

Copy the secrets template and fill in your server details:

```bash
cd tvos
cp Secrets.xcconfig.example Secrets.xcconfig
```

Edit `Secrets.xcconfig`:
```
BRG_SERVER_URL = http://YOUR_SERVER_IP:8080
BRG_API_KEY = your-api-key-here
```

### Build and package

```bash
cd tvos
xcodebuild -project KidsTube.xcodeproj \
  -scheme KidsTube \
  -destination "generic/platform=tvOS" \
  -configuration Release \
  CODE_SIGN_IDENTITY="-" \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGNING_ALLOWED=NO \
  ONLY_ACTIVE_ARCH=NO \
  build \
  CONFIGURATION_BUILD_DIR=/tmp/KidsTubeBuild

mkdir -p /tmp/KidsTubeIPA/Payload
cp -r /tmp/KidsTubeBuild/KidsTube.app /tmp/KidsTubeIPA/Payload/
cd /tmp/KidsTubeIPA && zip -r ~/Desktop/KidsTube.ipa Payload/
```

Upload the resulting `KidsTube.ipa` to your sideloading tool.

### Sideloading with atvloadly

[atvloadly](https://github.com/bitxeno/atvloadly) can install and auto-refresh the app wirelessly:

1. Run atvloadly on the same network as your Apple TV
2. Pair via Apple TV Settings > Remote and Devices > Remote App and Devices
3. Upload the IPA through the atvloadly web UI
4. atvloadly auto-refreshes before the 7-day free signing limit

Requires `avahi-daemon` on the host for mDNS discovery. Free Apple ID is fine (3-app limit).

## Telegram Bot Commands

Once running, message your bot on Telegram. Commands:

**Children**

| Command | Description |
|---|---|
| `/child` | List all profiles with summary |
| `/child add Name [Avatar]` | Add a child profile |
| `/child remove Name` | Delete a profile |
| `/child rename Old New` | Rename a profile |
| `/child Name` | Show single profile details |

**Content**

| Command | Description |
|---|---|
| `/pending` | View pending video requests |
| `/approved [Child]` | View approved videos |
| `/channel [Child]` | Manage channel allow/block lists |
| `/channel [Child] starter` | Browse and import starter channels |
| `/search` | Manage word filters (`/search add word`, `/search remove word`) |

**Activity**

| Command | Description |
|---|---|
| `/stats [Child]` | Video statistics (combined if child omitted) |
| `/watch [Child]` | Watch activity (combined if child omitted) |
| `/time [Child]` | View/set time limits and schedule |

Child name can be omitted when only one child exists.

Photo avatars: Send a photo to the bot with caption `avatar ChildName`.

## API Endpoints

All `/api/*` endpoints require `Authorization: Bearer <BRG_API_KEY>` except avatar serving and HLS segment delivery.

| Endpoint | Method | Description |
|---|---|---|
| `/api/profiles` | GET | List child profiles |
| `/api/profiles` | POST | Create child profile |
| `/api/profiles/{id}` | PUT | Update child profile |
| `/api/profiles/{id}` | DELETE | Delete child profile |
| `/api/profiles/{id}/avatar` | POST | Upload photo avatar |
| `/api/profiles/{id}/avatar` | GET | Serve photo avatar (public) |
| `/api/search` | GET | Search videos (params: `q`, `child_id`) |
| `/api/request` | POST | Request video approval |
| `/api/status/{video_id}` | GET | Poll approval status |
| `/api/stream/{video_id}` | GET | Get playable stream URL |
| `/api/catalog` | GET | Paginated approved video library |
| `/api/channels` | GET | List allowed channels |
| `/api/onboarding/starter-channels` | GET | Get curated starter channels |
| `/api/onboarding/import` | POST | Import starter channels for a child |
| `/api/watch-heartbeat` | POST | Report playback progress |
| `/api/time-status` | GET | Remaining time budget |
| `/api/schedule-status` | GET | Check schedule window |
| `/api/hls/{session_id}/{file}` | GET | Serve HLS segments (public) |
| `/api/hls/{session_id}` | DELETE | Clean up HLS session |

## Development

### Server tests

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

### tvOS tests

Open `tvos/KidsTube.xcodeproj` in Xcode and run the test target, or:

```bash
cd tvos
swift test
```

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md) for solutions to common issues including:

- Invidious won't start or health checks failing
- Telegram bot not responding (token/chat ID issues)
- Videos won't play (HLS/ffmpeg, stream URL expiry)
- tvOS app can't connect to server (network, API key mismatch)
- How to check logs (Docker Compose, server stdout)
- Database backup and restore (SQLite location, WAL mode)
- Common Invidious issues (rate limiting, Companion errors)

## Architecture Notes

- **Invidious stream URLs expire** after a few hours. The `/api/stream` endpoint fetches a fresh URL on every request.
- **HLS muxing**: When ffmpeg is available, the server muxes adaptive video+audio streams from Invidious into HLS on the fly. This gives better quality than progressive MP4 alone. Sessions are cleaned up after 2 hours or when the tvOS player dismisses.
- **Watch time** is tracked via heartbeats from the tvOS app (every 30 seconds). Server-side dedup prevents double-counting.
- **Channel allow/block lists are per-child**. A channel allowed for one child is not automatically allowed for another.
- **Video approvals are per-child**. Each child must independently have a video approved.
- **Starter channels** ([starter_channels.yaml](server/starter_channels.yaml)) provide curated content across educational, fun, music, and science categories for quick onboarding.

## License

MIT
