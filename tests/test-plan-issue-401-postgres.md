# Test Plan: 401 Handling & PostgreSQL Support

**Date:** 2026-03-28
**Issues:** 401 credential-clearing (frontend) + PostgreSQL backend support
**Author:** QA Analyst

---

## Overview

Two related changes being shipped together:

1. **Frontend (tvOS)** — When the app receives a 401 from the server, it must clear stored credentials and navigate to the pairing screen. This is the correct response to a revoked device key. The un-paired flow (no credentials) must not loop.
2. **Backend (Python/FastAPI)** — Add PostgreSQL as an alternative to SQLite. Same schema, same VideoStore API, selectable via config. Existing SQLite deployments must continue to work unchanged.

---

## Part 1: 401 Handling (tvOS Frontend)

### 1.1 Current State Analysis

- `APIClient.execute()` throws `APIError.httpError(statusCode: 401, ...)` on a 401 response.
- `ContentView` checks `CredentialStore.isPaired` to gate the pairing screen.
- `CredentialStore.clear()` is only called from `ProfileView.onUnpair` — there is **no** existing 401 handler.
- `PairingView` makes unauthenticated requests to `/api/pair/request` and `/api/pair/status/{token}`. These must not trigger 401 handling.

### 1.2 Expected Behavior After Change

| Scenario | Expected Result |
|---|---|
| Paired device gets 401 on any authenticated API call | Clear credentials, set `isPaired = false`, show PairingView |
| Unpaired device (no credentials) makes a call | No credentials to clear; pairing screen already visible |
| Multiple concurrent API calls all return 401 | Credentials cleared exactly once, no race condition |
| 401 during pairing poll (`/api/pair/status`) | Should NOT trigger credential clearing (no auth on this endpoint) |
| Non-401 error (500, network error) | No credential clearing, normal error handling |

### 1.3 Test Cases

#### TC-401-01: Paired device 401 clears credentials and shows pairing screen
- **Setup:** App is paired (`CredentialStore.isPaired == true`), server returns 401 on next call
- **Expected:** `CredentialStore.isPaired` becomes false, `ContentView` shows `PairingView`
- **Risk:** `isPaired` is `@State` — must verify it is updated on main actor and triggers view update

#### TC-401-02: No infinite loop when credentials are already absent
- **Setup:** `CredentialStore` is empty, app shows `PairingView`
- **Expected:** `PairingView` makes unauthenticated pairing requests. No 401 is thrown. No recursive clear.
- **Risk:** If pairing endpoint accidentally sends auth header when `apiKey` is empty, verify `applyAuth()` guards correctly (`if !apiKey.isEmpty`)

#### TC-401-03: Race condition — two simultaneous 401 responses
- **Setup:** Two concurrent API calls both return 401
- **Expected:** `CredentialStore.clear()` is called (idempotent), `isPaired` set to false once
- **Risk:** If credential clearing is not guarded, multiple transitions to pairing screen could cause view state corruption

#### TC-401-04: 401 from heartbeat/background task
- **Setup:** App is in background, heartbeat fires and gets 401
- **Expected:** Graceful navigation to pairing screen; no crash, no dangling background tasks
- **Risk:** `HeartbeatService` and `TimeRequestService` run async tasks; must handle 401 without crashing

#### TC-401-05: 401 from pairing-related endpoints (should NOT clear credentials)
- **Setup:** Calling `/api/pair/status/{token}` or `/api/pair/request` — these use unauthenticated `execute()` bypassing `applyAuth()`
- **Expected:** A 4xx from these endpoints does NOT invoke credential clearing
- **Risk:** If a global 401 handler is added to `execute()`, it must be skipped for pairing endpoints

#### TC-401-06: Transition to pairing screen from mid-session state
- **Setup:** Child profile is selected, time tracking is active, then 401 occurs
- **Expected:** All overlays dismissed, child deselected, pairing screen shown cleanly
- **Risk:** `selectedChild`, `overlayScreen`, `playerItem`, background tasks must all be cleaned up

#### TC-401-07: Config.swift uses CredentialStore at runtime after re-pairing
- **Setup:** Pair, use app, get 401, re-pair with new credentials
- **Expected:** New API key from `CredentialStore.apiKey` is used by `APIClient` on next construction
- **Risk:** `Config.apiKey` and `Config.serverBaseURL` — if these are cached at app launch (static let) rather than reading from CredentialStore dynamically, re-pairing won't work

---

## Part 2: PostgreSQL Support (Backend)

### 2.1 Current State Analysis

- `VideoStore.__init__` takes a `db_path: str` for SQLite
- `config.py` has `DatabaseConfig.path: str = "db/videos.db"` — SQLite only
- All DB operations use `sqlite3` with `conn.row_factory = sqlite3.Row`
- Schema uses SQLite-specific syntax: `INTEGER PRIMARY KEY AUTOINCREMENT`, `PRAGMA journal_mode=WAL`, `datetime('now')`

### 2.2 Expected Behavior After Change

- New config option (e.g., `database.backend: sqlite|postgres`, `database.dsn`) selects the backend
- `VideoStore` (or a new abstraction) exposes the same public API regardless of backend
- All existing server tests continue to pass unchanged against SQLite
- PostgreSQL backend passes the same tests when pointed at a real or test PG instance
- No SQLite-isms leak into PostgreSQL path (e.g., `AUTOINCREMENT` → `SERIAL`/`BIGSERIAL`, `datetime('now')` → `NOW()`)

### 2.3 Test Cases

#### TC-PG-01: Config loads SQLite by default
- **Setup:** No `database.backend` in config / env vars
- **Expected:** `VideoStore` opens SQLite at `database.path`, all existing tests pass
- **Risk:** Regression — any new config keys must have safe defaults

#### TC-PG-02: Config switches to PostgreSQL via env var
- **Setup:** `BRG_DB_BACKEND=postgres`, `BRG_DB_DSN=postgresql://...`
- **Expected:** `VideoStore` (or postgres implementation) connects to PG, returns same data model
- **Risk:** Connection string parsing, SSL options, connection pool config

#### TC-PG-03: Schema parity — all tables exist in PostgreSQL
- **Expected tables:** `children`, `child_settings`, `videos`, `child_video_access`, `watch_log`, `channels`, `child_channels`, `channel_requests`, `word_filters`, `settings`, `search_log`, `pairing_sessions`, `paired_devices`
- **Risk:** Missed tables or columns in the PG migration script

#### TC-PG-04: AUTOINCREMENT → SERIAL equivalence
- **Expected:** Insert a row without specifying `id`; verify auto-increment works and returned id is correct
- **Risk:** SQLite uses `INTEGER PRIMARY KEY AUTOINCREMENT`, PostgreSQL uses `SERIAL` or `GENERATED ALWAYS AS IDENTITY`

#### TC-PG-05: `datetime('now')` → `NOW()` / `CURRENT_TIMESTAMP`
- **Expected:** Timestamp columns are populated correctly on insert
- **Risk:** SQLite uses string timestamps in `YYYY-MM-DD HH:MM:SS` format; PG uses proper timestamp types; code that parses these must handle both

#### TC-PG-06: Full CRUD — children profiles
- **Expected:** `create_child()`, `get_children()`, `delete_child()` work correctly in PG
- **Test:** Create 3 profiles, read them back, delete one, verify list has 2

#### TC-PG-07: Full CRUD — video approval flow
- **Expected:** `request_video()`, `approve_video()`, `deny_video()`, `get_video_status()` work in PG
- **Test:** Request video, check pending status, approve, check approved status

#### TC-PG-08: Full CRUD — pairing sessions
- **Expected:** `create_pairing_session()`, `get_pairing_session()`, `confirm_pairing()`, `get_paired_devices()`, `revoke_device()` work in PG
- **Risk:** Token uniqueness, UUID generation if changed from secrets.token_urlsafe

#### TC-PG-09: Concurrent writes with threading lock
- **Expected:** `VideoStore._lock` still serializes access; no deadlocks with PG connection pool
- **Risk:** SQLite uses a single connection; PG may use a connection pool — lock semantics may need adjustment

#### TC-PG-10: Connection error handling
- **Setup:** PostgreSQL DSN points to unavailable server
- **Expected:** Startup fails with a clear error message, not a cryptic exception
- **Risk:** Connection error should surface before server starts accepting requests

#### TC-PG-11: Migration compatibility for existing SQLite databases
- **Setup:** Existing SQLite DB with `_migrate()` applied; switch to PG backend
- **Expected:** PG schema is initialized fresh (no migration conflict); SQLite DB is unaffected
- **Risk:** If migration state is stored in DB, it must be backend-specific

#### TC-PG-12: SQLite `_migrate()` still runs for SQLite backend
- **Expected:** After adding PG support, the `_migrate()` function still applies missing columns to existing SQLite databases
- **Risk:** Refactoring VideoStore init could break the migration path

---

## Part 3: Integration Tests

### 3.1 End-to-End: Device pairing → 401 → re-pair

**Scenario:** Full lifecycle test
1. TV app pairs with server (SQLite backend) → credentials stored in Keychain
2. Parent revokes device via `DELETE /api/devices/{id}`
3. TV app makes next API call → receives 401
4. TV app clears credentials, shows pairing screen
5. TV re-pairs → new device key issued
6. TV makes API call with new key → succeeds

**Risk areas:**
- Step 3: 401 handling must be in the right place in the call chain
- Step 4: `isPaired` state update must trigger view re-render
- Step 6: `Config.apiKey` must read new value from `CredentialStore`

### 3.2 API Contract: Auth flow with both backends

**Expected:** The pairing API endpoints (`/api/pair/*`, `/api/devices`) behave identically regardless of SQLite vs PG backend.

| Check | SQLite | PostgreSQL |
|---|---|---|
| `POST /api/pair/request` returns token + PIN | ✓ baseline | must match |
| `GET /api/pair/status/{token}` shows pending | ✓ baseline | must match |
| `POST /api/pair/confirm/{token}` returns api_key | ✓ baseline | must match |
| `GET /api/devices` lists paired device | ✓ baseline | must match |
| `DELETE /api/devices/{id}` revokes key | ✓ baseline | must match |
| Revoked key gets 401 | ✓ baseline | must match |

---

## Risks & Concerns to Flag

1. **`Config.apiKey` static init** — If `Config.apiKey` is a `static let` initialized once at app launch from `CredentialStore`, re-pairing won't pick up the new key. Must be dynamic.
2. **Background task cleanup on 401** — `HeartbeatService`, periodic status checks must be cancelled before navigating to pairing screen to prevent zombie tasks re-triggering 401.
3. **Thread-safety of `CredentialStore.clear()`** — Keychain operations are generally thread-safe, but the `isPaired` @State update must happen on MainActor.
4. **PostgreSQL `row_factory` equivalent** — SQLite uses `conn.row_factory = sqlite3.Row` for dict-like rows. PostgreSQL with `psycopg2` needs `RealDictCursor` or similar. Row access patterns must be consistent.
5. **SQLite WAL mode** — Only applicable to SQLite. Must not be attempted on PG connection.
6. **`PRAGMA foreign_keys=ON`** — SQLite-specific. PG has FK enforcement by default.

---

## Pre-Review Code Observations (Phase 1 Findings)

### Confirmed Risks

**Risk A — `HeartbeatService` and `TimeRequestService` store a private `APIClient` instance.**
Both services initialize `private let apiClient: APIClient` at construction time. Both swallow all errors silently. If 401 handling is implemented as a callback/notification from `APIClient.execute()`, these stored clients must participate, or they will silently continue with the revoked key indefinitely.

**Risk B — `Config.apiKey` and `Config.serverBaseURL` are `static var` (computed), not `static let`.**
This is good: they re-read from `CredentialStore` on every call. New `APIClient()` instances will automatically pick up fresh credentials after re-pairing. No risk here.

**Risk C — `ContentView` creates `APIClient()` inline per-call.**
All calls in `ContentView` use `let apiClient = APIClient()` locally. Good — these will use fresh credentials. But `HeartbeatService` and `TimeRequestService` are different (see Risk A).

**Risk D — No existing 401 handling anywhere.**
Confirmed: `APIClient.execute()` throws `APIError.httpError(statusCode: 401, ...)` but nothing catches it to clear credentials. This is the gap being fixed.

### Baseline Test Results (2026-03-28)

| Suite | Result |
|---|---|
| `server/` pytest | **773 passed, 1 pre-existing failure** |
| `tvos/` swift test | **133 passed, 0 failed** |

**Pre-existing server failure** (not related to these issues):
```
FAILED tests/test_category_time.py::TestCategoryWatchMinutes::test_counts_matching_category
assert 0.0 == 10.0 ± 1.0e-01
```
This failure exists on `main` before any changes. The Phase 2 review should expect this failure to persist unchanged.

---

## Test Execution Plan

### Phase 1 (Now — before dev completion)
- [x] Review existing code for 401 handling gaps
- [x] Review existing code for PostgreSQL readiness
- [x] Write this test plan

### Phase 2 (After both devs message QA)
- [ ] Read all changed files from frontend-dev and backend-dev
- [ ] Run `cd server && source .venv/bin/activate && pytest`
- [ ] Run `cd tvos && swift test`
- [ ] Manually verify each TC above against implementation
- [ ] Write final report to `tests/report-issue-401-postgres.md`
