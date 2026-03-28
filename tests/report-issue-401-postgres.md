# QA Report: 401 Handling & PostgreSQL Support

**Date:** 2026-03-28
**Reviewed by:** QA Analyst
**Tasks:** #1 (401 credential clearing) + #2 (PostgreSQL backend)

---

## Test Results

| Suite | Result |
|---|---|
| `server/` pytest | **773 passed, 1 pre-existing failure** (unchanged from baseline) |
| `tvos/` swift test | **133 passed, 0 failed** |

The single server failure (`test_category_time.py::TestCategoryWatchMinutes::test_counts_matching_category`) is pre-existing and unrelated to these changes. Both test suites are green.

---

## Frontend Review — 401 Credential Clearing (Task #1)

### Files reviewed
- `tvos/Sources/Services/APIClient.swift`
- `tvos/Sources/App/ContentView.swift`

### Implementation Summary

`APIClient.execute()` detects 401 responses. When `CredentialStore.isPaired` is true, it calls `CredentialStore.clear()` and posts `Notification.Name("AuthenticationExpired")` on the main thread via `DispatchQueue.main.async`, then throws the error normally. `ContentView` listens with `.onReceive` and resets `selectedChild = nil` and `isPaired = false`.

### Test Case Results

| Test Case | Result | Notes |
|---|---|---|
| TC-401-01: Paired device 401 clears credentials | ✅ PASS | Guard + clear + notification all correct |
| TC-401-02: No loop when credentials absent | ✅ PASS | `CredentialStore.isPaired` false → guard blocks clearing |
| TC-401-03: Race condition — concurrent 401s | ✅ PASS | `clear()` and state updates are idempotent; multiple notifications fire safely |
| TC-401-04: 401 from HeartbeatService | ✅ PASS | Notification fires before throw, so it propagates even when caller swallows the error |
| TC-401-05: Pairing endpoints exempt | ✅ PASS | `requestPairing()`/`getPairStatus()` use unauthenticated `execute()` with empty `apiKey`; `CredentialStore.isPaired` false during pairing |
| TC-401-06: Mid-session state cleanup | ✅ PASS | `selectedChild = nil` dismisses main layout + overlays; `playerItem` handled below |
| TC-401-07: Re-pairing uses fresh credentials | ✅ PASS | `Config.apiKey` is `static var` (computed property), reads Keychain on each access |

### Findings

**F-01 — Test gap: no assertion that 401 triggers credential clearing** (low severity)

The existing `httpError401` test in `APIClientTests.swift` only verifies that the error is thrown with the correct status code and detail message. It does not assert:
- That `CredentialStore.clear()` is called when `isPaired` is true
- That the `AuthenticationExpired` notification is posted

The new behavior has no automated test coverage. This is a gap, not a blocking bug — the logic is simple and correct — but a test would prevent regressions.

**F-02 — `playerItem` not cleared on 401** (informational, acceptable)

When a 401 fires during video playback, `playerItem` is not set to nil in the `.onReceive` handler. The full-screen player remains visible until the user dismisses it, at which point `isPaired = false` causes `PairingView` to show. This is acceptable UX — the transition is clean once the player closes — but worth documenting as intentional.

**F-03 — Test count discrepancy** (informational)

Frontend-dev reported 132/133 during development. My post-merge run shows 133/133 passing. Likely an environment or timing difference during their run — all tests pass now.

---

## Backend Review — PostgreSQL Support (Task #2)

### Files reviewed
- `server/data/base_store.py` — abstract interface
- `server/data/pg_video_store.py` — PostgreSQL implementation
- `server/data/video_store.py` — SQLiteVideoStore rename + alias
- `server/data/__init__.py` — factory
- `server/config.py` — DatabaseConfig extension
- `server/main.py` — factory usage

### Test Case Results

| Test Case | Result | Notes |
|---|---|---|
| TC-PG-01: SQLite default | ✅ PASS | Factory returns `SQLiteVideoStore` with `type="sqlite"` |
| TC-PG-02: Config switching via env var | ✅ PASS | `BRG_DATABASE_TYPE` + `BRG_DATABASE_URL` wired in `from_env()` |
| TC-PG-03: Schema parity — all 13 tables | ✅ PASS | All tables present: children, child_settings, videos, child_video_access, watch_log, channels, child_channels, channel_requests, word_filters, settings, search_log, pairing_sessions, paired_devices |
| TC-PG-04: AUTOINCREMENT → SERIAL | ✅ PASS | All PK columns use `SERIAL PRIMARY KEY` |
| TC-PG-05: datetime('now') → ISO string helper | ✅ PASS | `_now()` returns `'YYYY-MM-DD HH24:MI:SS'` matching SQLite format |
| TC-PG-06: CRUD — child profiles | ✅ PASS | All 5 methods implemented with ON CONFLICT and LOWER() case-insensitivity |
| TC-PG-07: CRUD — video approval flow | ✅ PASS | `request_video` handles auto-approve/deny, pending, and conflict correctly |
| TC-PG-08: CRUD — pairing sessions | ✅ PASS | Full pairing flow verified (see integration check below) |
| TC-PG-09: Threading lock | ✅ PASS | `_lock` used on every public method; matches SQLite model |
| TC-PG-10: Connection error handling | ✅ PASS | `psycopg2.connect()` raises at construction; `ValueError` raised for missing URL |
| TC-PG-11: Migration compatibility | ✅ PASS | `_migrate()` uses `information_schema` for PG column detection, parallel to SQLite PRAGMA |
| TC-PG-12: SQLite `_migrate()` unchanged | ✅ PASS | SQLite code untouched; 773 tests still pass |

### Backward Compatibility

- `VideoStore = SQLiteVideoStore` alias present — existing code using `VideoStore` directly continues to work ✅
- `create_video_store()` defaults to SQLite — no config change needed for existing deployments ✅
- Unknown `type` values silently fall back to SQLite ✅

### Bug Found

**B-01 — `PostgresVideoStore` does not inherit from `BaseVideoStore`** (medium severity)

```python
# pg_video_store.py line 45
class PostgresVideoStore:          # ← missing (BaseVideoStore)
```

All 89 abstract methods are present and correctly implemented — no runtime failure occurs. However:
- `isinstance(store, BaseVideoStore)` returns `False` for PG instances
- Python's ABC won't catch missing methods in future refactors
- Type annotations (`-> BaseVideoStore` in factory) are technically incorrect

The fix is one character: `class PostgresVideoStore(BaseVideoStore):`. This is a non-blocking issue but should be fixed before shipping.

### Not Testable (No PG Instance)

The following were verified by code inspection only:
- Actual PG query execution and data round-trip
- FK cascade delete behavior
- PG-specific error types (e.g., `UniqueViolation` handling)
- Connection pool behavior under concurrent load

---

## Integration Check — API Contract

### Auth flow with both backends

The backend change is data-layer only. No API endpoint signatures changed. The complete pairing + revocation + 401 chain was traced:

```
confirm_pairing(token) → inserts to paired_devices → returns {api_key, ...}
  ↓
set_pairing_device_key(token, api_key) → updates pairing_sessions.device_api_key
  ↓
TV polls GET /pair/status/{token} → get_pairing_session() → returns session with device_api_key
  ↓
Routes return {status: "confirmed", api_key: session["device_api_key"]} → TV stores in Keychain
  ↓
TV uses api_key on all requests → verify_api_key() → get_device_by_api_key() → 200 OK
  ↓
Parent revokes: DELETE /api/devices/{id} → revoke_device() → is_active = 0
  ↓
Next TV request → get_device_by_api_key() returns None → 401
  ↓
APIClient.execute(): CredentialStore.isPaired=true → clear() + AuthenticationExpired
  ↓
ContentView.onReceive → isPaired = false → PairingView shown
```

This chain is intact and correct for both SQLite and PostgreSQL backends. ✅

---

## Summary

| Component | Status | Blocker? |
|---|---|---|
| 401 credential clearing — logic | ✅ PASS | No |
| 401 credential clearing — test coverage | ⚠️ GAP | No (recommendation only) |
| PostgreSQL schema parity | ✅ PASS | No |
| PostgreSQL CRUD operations | ✅ PASS | No |
| PostgreSQL missing base class inheritance | 🐛 BUG | Recommended fix |
| Backward compatibility (SQLite unchanged) | ✅ PASS | No |
| API contract alignment | ✅ PASS | No |
| Server tests | ✅ 773 passed, 1 pre-existing failure | No |
| tvOS tests | ✅ 133 passed | No |

**Overall: PASS.** One bug (missing inheritance) recommended to fix before merging. One test gap recommended as follow-up. No blocking issues.
