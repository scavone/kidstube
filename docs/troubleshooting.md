# Troubleshooting

This guide covers common issues with KidsTube, organized by component. Each section describes symptoms, likely causes, and resolution steps with copy-pasteable diagnostic commands.

## Table of Contents

- [Checking Logs](#checking-logs)
- [Invidious Won't Start / Health Check Failing](#invidious-wont-start--health-check-failing)
- [Common Invidious Issues](#common-invidious-issues)
- [Telegram Bot Not Responding](#telegram-bot-not-responding)
- [Videos Won't Play](#videos-wont-play)
- [tvOS App Can't Connect to Server](#tvos-app-cant-connect-to-server)
- [Database Backup and Restore](#database-backup-and-restore)

---

## Checking Logs

Before diving into specific issues, know how to access logs for each component.

### Docker Compose

If running all services via Docker Compose:

```bash
# All services
docker compose logs

# Follow logs in real time
docker compose logs -f

# Specific service (last 100 lines)
docker compose logs --tail=100 kidstube-server
docker compose logs --tail=100 invidious
docker compose logs --tail=100 invidious-companion
```

### KidsTube Server (standalone)

The server logs to stdout with the format:

```
2025-01-15 10:30:00,123 [api.routes] INFO: Starting request...
```

Key logger names to watch for:

| Logger | What it covers |
|--------|---------------|
| `__main__` | Server startup and shutdown |
| `config` | Configuration loading |
| `api.routes` | API requests, HLS session management |
| `api.auth` | Authentication failures |
| `bot.telegram_bot` | Telegram bot events |
| `invidious.client` | Invidious API calls |
| `services.channel_refresher` | Background channel refresh |
| `data.video_store` | Database operations |

### Invidious

Invidious logs to stdout. Look for lines containing `[ERROR]` or `[WARN]`. Companion logs separately — check both when diagnosing stream issues.

---

## Invidious Won't Start / Health Check Failing

### Symptoms

- Invidious container exits immediately or keeps restarting
- Health check endpoint returns errors or times out
- KidsTube server logs: `Could not resolve video from Invidious`

### Likely Causes and Fixes

**PostgreSQL not ready or misconfigured**

Invidious requires PostgreSQL. If the database isn't reachable, Invidious will crash on startup.

```bash
# Check if PostgreSQL is running
docker compose ps postgres

# Test database connectivity from the Invidious container
docker compose exec invidious sh -c 'nc -zv <postgres-host> 5432'

# Check Invidious logs for DB errors
docker compose logs invidious | grep -i "database\|postgres\|PG::"
```

Verify your Invidious `config.yml` database section:

```yaml
db:
  dbname: invidious
  user: kemal
  password: <your-password>
  host: <postgres-host>
  port: 5432
check_tables: true
```

**Missing `local: true` in Invidious config**

KidsTube requires Invidious to proxy video streams. Without `local: true`, Invidious returns direct YouTube URLs that the Apple TV cannot reach.

```yaml
# Required in Invidious config.yml
local: true
```

**Companion not configured or unreachable**

Invidious Companion handles stream URL resolution. If it's down or misconfigured, video lookups fail silently or return errors.

```bash
# Check Companion is running
docker compose ps invidious-companion

# Test Companion from the Invidious container
docker compose exec invidious sh -c 'curl -s http://<companion-host>:8282'

# Check Companion logs
docker compose logs invidious-companion
```

Verify the Invidious config includes the Companion block:

```yaml
invidious_companion:
  - private_url: http://<companion-host>:8282
```

**Port mismatch**

KidsTube expects Invidious at the URL configured in `BRG_INVIDIOUS_URL` (default: `http://invidious:3000`). Verify the hostname and port match your actual Invidious instance:

```bash
# Test connectivity from the KidsTube server
curl -s http://invidious:3000/api/v1/stats
```

---

## Common Invidious Issues

### Rate Limiting / HTTP 429 Errors

**Symptoms**: Searches return no results, video metadata fails intermittently, Invidious logs show `429` or `Too Many Requests`.

**Cause**: YouTube rate-limits requests from the Invidious instance's IP address.

**Resolution**:
- Reduce search frequency and channel refresh interval:
  ```bash
  # Increase refresh interval (default is 6 hours)
  BRG_CHANNEL_REFRESH_HOURS=12
  ```
- Ensure Invidious Companion is properly configured — it helps distribute requests
- Check the [Invidious issues tracker](https://github.com/iv-org/invidious/issues) for current YouTube-side breakages

### Companion Errors / Stream Resolution Failures

**Symptoms**: Videos found in search but won't play. Server logs: `No playable streams found` or `Could not resolve video from Invidious`.

**Cause**: Invidious Companion is not resolving stream URLs correctly. This can happen after YouTube changes their API.

**Resolution**:
- Update Companion to the latest version:
  ```bash
  docker compose pull invidious-companion
  docker compose up -d invidious-companion
  ```
- Check Companion logs for specific errors:
  ```bash
  docker compose logs --tail=50 invidious-companion
  ```
- Verify Companion is reachable from Invidious (see the connectivity test above)
- Check [Invidious Companion issues](https://github.com/iv-org/invidious-companion/issues) for known breakages

### Stale or Missing Video Data

**Symptoms**: Channel videos not appearing, search results seem outdated.

**Cause**: Channel refresh hasn't run, or Invidious's internal cache is stale.

**Resolution**:
- The KidsTube channel refresher runs every 6 hours by default. Check when it last ran:
  ```bash
  docker compose logs kidstube-server | grep "channel_refresher"
  ```
- Restart the server to trigger an immediate refresh cycle
- Invidious itself caches channel data for 30 minutes (configurable via `BRG_CHANNEL_CACHE_TTL`)

---

## Telegram Bot Not Responding

### Symptoms

- No response to `/start` or any command in Telegram
- Server logs: `No Telegram bot token configured — bot disabled`
- Approval notifications not arriving

### Likely Causes and Fixes

**Bot token not set or invalid**

```bash
# Check if the token is configured
echo $BRG_BOT_TOKEN

# Test the token directly with the Telegram API
curl -s "https://api.telegram.org/bot${BRG_BOT_TOKEN}/getMe"
```

A valid response includes `"ok": true` with your bot's username. If you get `"ok": false`, the token is invalid — regenerate it via [@BotFather](https://t.me/BotFather).

**Admin chat ID not set or wrong**

The bot only responds to the chat ID in `BRG_ADMIN_CHAT_ID`. If this is empty or wrong, all commands are silently ignored.

```bash
# Check current value
echo $BRG_ADMIN_CHAT_ID
```

To find your chat ID:
1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. It replies with your numeric chat ID
3. Set `BRG_ADMIN_CHAT_ID` to that number

The server logs a warning on startup if the chat ID is empty:

```
telegram.admin_chat_id is empty — bot commands will be unauthorized
```

**Non-numeric chat ID**

`BRG_ADMIN_CHAT_ID` must be a numeric value. Usernames or other strings won't work and the admin authorization check will fail silently.

**Bot not started in Telegram**

You must send `/start` to the bot in Telegram at least once before it can send you messages. If you've never started a conversation with the bot, approval notifications will fail silently.

**Network issues (container can't reach Telegram API)**

```bash
# Test outbound connectivity from the server container
docker compose exec kidstube-server sh -c 'curl -s https://api.telegram.org'
```

If this fails, check your container's DNS and outbound internet access.

---

## Videos Won't Play

### Symptoms

- tvOS app shows "Stream Unavailable" or stays on the loading screen
- Server returns HTTP 502 or 504 on `/api/stream/{video_id}`
- Audio plays but no video (or vice versa)

### Likely Causes and Fixes

**ffmpeg not installed**

The server uses ffmpeg for HLS adaptive streaming. Without it, it falls back to progressive MP4 or Invidious HLS URLs — which may not work for all videos.

```bash
# Check if ffmpeg is available
which ffmpeg
ffmpeg -version

# In Docker, ffmpeg is pre-installed in the official image
docker compose exec kidstube-server which ffmpeg
```

If running the server directly (not Docker), install ffmpeg:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

**Stream URL expiry**

Invidious stream URLs expire after a few hours. The server fetches a fresh URL on every `/api/stream` request, so this should be transparent. If you see stale URL errors:

- Check that Invidious is reachable (see above)
- Look for `Could not resolve video from Invidious` in server logs
- The video may have been removed from YouTube

**HLS muxing failures**

```bash
# Check for ffmpeg errors in server logs
docker compose logs kidstube-server | grep -i "ffmpeg\|hls"
```

Common ffmpeg-related log messages:

| Log message | Meaning |
|------------|---------|
| `HLS session {id} started for {video_id}` | Muxing started normally |
| `ffmpeg HLS failed for {video_id}: ...` | ffmpeg crashed — check the stderr snippet |
| `HLS segment generation timed out` | First segment not ready in 30 seconds |
| `Cleaned up HLS session {id}` | Normal cleanup |

**HLS session timeout (HTTP 504)**

If the server returns 504 "HLS segment generation timed out", ffmpeg couldn't produce the first segment within 30 seconds. This usually means:

- The Invidious stream URL is unreachable or very slow
- The server's temp directory is full:
  ```bash
  df -h /tmp
  ```
- The video's adaptive streams are in an unusual format

**No playable streams (HTTP 502)**

If the server returns 502 "No playable streams found", the video either has no compatible adaptive or progressive streams, or Invidious returned incomplete data. Try the video on the Invidious web UI directly to verify.

---

## tvOS App Can't Connect to Server

### Symptoms

- App shows a connection error or blank screen on launch
- Profile picker loads but searches/requests fail
- HTTP 401 errors in server logs

### Likely Causes and Fixes

**Server not reachable from the Apple TV**

The Apple TV must be able to reach the server on port 8080 (or your configured `BRG_WEB_PORT`).

```bash
# From another device on the same network, test connectivity
curl -s http://<server-ip>:8080/api/profiles \
  -H "Authorization: Bearer <your-api-key>"
```

Check:
- Server is running and listening (`Starting KidsTube server on 0.0.0.0:8080` in logs)
- Firewall allows traffic on port 8080
- Apple TV and server are on the same network (or routing exists between them)

**API key mismatch**

The tvOS app sends `Authorization: Bearer <key>` on every request. If the key in `Secrets.xcconfig` doesn't match the server's `BRG_API_KEY`, all requests get HTTP 401.

Server-side, look for these log entries:

```
Invalid API key
Missing or invalid Authorization header
```

To fix:
1. Check the server's `BRG_API_KEY` value
2. In `tvos/Secrets.xcconfig`, ensure `BRG_API_KEY` matches exactly (no trailing spaces or quotes)
3. Rebuild and re-deploy the tvOS app after changing `Secrets.xcconfig`

**Wrong server URL in tvOS app**

The tvOS app reads its server URL from `Secrets.xcconfig` at build time. If the URL is wrong, it falls back to `http://localhost:8080` (which won't work on an Apple TV).

In `tvos/Secrets.xcconfig`:

```
BRG_SERVER_URL = http://<your-server-ip>:8080
BRG_API_KEY = <your-api-key>
```

After changing, rebuild and re-sideload the app.

**Dev mode (empty API key)**

If `BRG_API_KEY` is empty on the server, authentication is disabled (dev mode). This is fine for local development but insecure for production. If the tvOS app sends a key but the server has none set, requests will still succeed — the server skips auth entirely when the key is empty.

---

## Database Backup and Restore

### SQLite File Location

The database is a single SQLite file:

| Setup | Default path |
|-------|-------------|
| Docker | `/app/db/videos.db` (inside the container) |
| Direct | `server/db/videos.db` (relative to working directory) |
| Custom | Set via `BRG_DB_PATH` environment variable |

The directory is created automatically on first run. In Docker, mount a persistent volume at `/app/db` to survive container restarts.

### WAL Mode Considerations

KidsTube enables SQLite WAL (Write-Ahead Logging) mode. This means the database may have up to three files:

```
videos.db        # Main database file
videos.db-wal    # Write-ahead log (pending writes)
videos.db-shm    # Shared memory index
```

**Important**: When backing up, you must copy all three files together, or the backup may be incomplete or corrupted.

### Backup

**Safe backup (while server is running):**

```bash
# Using sqlite3's built-in backup (recommended)
sqlite3 /app/db/videos.db ".backup '/tmp/videos_backup.db'"

# Then copy the backup file to your backup location
cp /tmp/videos_backup.db /path/to/backups/videos_$(date +%Y%m%d).db
```

The `.backup` command is atomic and safe to run while the server is writing.

**Docker backup:**

```bash
# Copy the database out of the container safely
docker compose exec kidstube-server \
  sqlite3 /app/db/videos.db ".backup '/tmp/videos_backup.db'"
docker compose cp kidstube-server:/tmp/videos_backup.db ./videos_backup.db
```

**Quick file copy (stop server first):**

```bash
# Stop the server to ensure WAL is flushed
docker compose stop kidstube-server

# Copy all database files
cp /app/db/videos.db /path/to/backups/
cp /app/db/videos.db-wal /path/to/backups/ 2>/dev/null
cp /app/db/videos.db-shm /path/to/backups/ 2>/dev/null

# Restart
docker compose start kidstube-server
```

### Restore

```bash
# Stop the server
docker compose stop kidstube-server

# Replace the database
cp /path/to/backups/videos_backup.db /app/db/videos.db

# Remove stale WAL files (the backup won't have them)
rm -f /app/db/videos.db-wal /app/db/videos.db-shm

# Restart — schema migrations will run automatically if needed
docker compose start kidstube-server
```

### Checking Database Integrity

```bash
sqlite3 /app/db/videos.db "PRAGMA integrity_check;"
```

A healthy database returns `ok`. Any other output indicates corruption — restore from a backup.

### Viewing Database Contents

```bash
# List tables
sqlite3 /app/db/videos.db ".tables"

# Count records in key tables
sqlite3 /app/db/videos.db "
  SELECT 'children' AS tbl, COUNT(*) FROM children
  UNION ALL SELECT 'videos', COUNT(*) FROM videos
  UNION ALL SELECT 'child_video_access', COUNT(*) FROM child_video_access
  UNION ALL SELECT 'child_channels', COUNT(*) FROM child_channels
  UNION ALL SELECT 'watch_log', COUNT(*) FROM watch_log;
"
```
