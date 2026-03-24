# Issue #8 Integration Report: QR Code / PIN Code Pairing

**Date:** 2026-03-24
**Issue:** #8 — QR code / pin code pairing to replace hardcoded server credentials
**Status:** Ready for merge

---

## Phase 1: Test Plans

- **Backend tests:** `server/tests/test_pairing_endpoint.py` — 34 tests across 6 suites
  - TestPairRequestEndpoint (6 tests)
  - TestPairStatusEndpoint (4 tests)
  - TestPairConfirmEndpoint (8 tests)
  - TestPairingSecurity (5 tests)
  - TestPinValidation (2 tests)
  - TestDeviceManagement (4 tests)

- **Frontend tests:** `tvos/Tests/PairingTests.swift` — Test plan documented (commented out, awaiting Package.swift inclusion of pairing models). Covers PairingSession decode, PairingStatus decode, APIClient pairing methods, KeychainService (requires tvOS SDK), and manual QA checklist.

## Phase 2: Integration Review

### Endpoint Alignment

| Endpoint | Backend | Frontend | Match |
|----------|---------|----------|-------|
| Request pairing | `POST /api/pair/request` | `APIClient.requestPairing()` → `/api/pair/request` | YES |
| Poll status | `GET /api/pair/status/{token}` | `APIClient.getPairStatus(token:)` → `/api/pair/status/{token}` | YES |
| Confirm (admin) | `POST /api/pair/confirm/{token}` | N/A (admin only) | N/A |
| Confirm by PIN | `POST /api/pair/confirm-by-pin` | N/A (admin only) | N/A |
| List devices | `GET /api/devices` | N/A (admin only) | N/A |
| Revoke device | `DELETE /api/devices/{device_id}` | N/A (admin only) | N/A |

All tvOS-facing endpoints match correctly.

### Model Alignment

**PairRequestResponse:**

| Field | Backend (Pydantic) | Frontend (Swift CodingKey) | Match |
|-------|--------------------|---------------------------|-------|
| `token` | `str` | `String` | YES |
| `pin` | `str` | `String` | YES |
| `expires_at` | `str` | `String` (`"expires_at"`) | YES |
| `expires_in` | `int` | `Int` (`"expires_in"`) | YES |

**PairStatusResponse:**

| Field | Backend (Pydantic) | Frontend (Swift CodingKey) | Match |
|-------|--------------------|---------------------------|-------|
| `status` | `str` | `String` | YES |
| `api_key` | `Optional[str]` | `String?` (`"api_key"`) | YES |
| `server_url` | `Optional[str]` | `String?` (`"server_url"`) | YES |

All fields align correctly between backend and frontend models.

### Authentication Changes

**`server/api/auth.py`** — Updated to accept both master and device API keys:
1. Checks master `BRG_API_KEY` first (constant-time comparison via `hmac.compare_digest`)
2. Falls back to `video_store.get_device_by_api_key()` for paired device keys
3. Updates `last_seen_at` timestamp on each authenticated device request
4. Empty API key still skips auth (dev mode preserved)

This correctly allows paired devices to authenticate with their issued keys.

### Credential Storage & Config Integration

**`CredentialStore`** wraps `KeychainService` for paired credentials:
- `store(serverURL:apiKey:)` — saves both values, normalizes trailing slash
- `isPaired` — computed property checking both URL and key exist
- `clear()` — deletes both values (used by "Forget Server")

**`Config`** resolution order:
1. `CredentialStore.serverURL` / `CredentialStore.apiKey` (Keychain — set during pairing)
2. `Info.plist` via `BRGServerURL` / `BRGAPIKey` (build-time config)
3. Fallback defaults (`http://localhost:8080` / empty string)

This is correct — paired credentials take priority, with backward compatibility for existing build-time config.

### Keychain Security

**`KeychainService`** uses:
- `kSecClassGenericPassword` with service name `com.kidstube.app`
- `kSecAttrAccessibleAfterFirstUnlock` — available after first device unlock, survives reboots
- Delete-before-save pattern prevents duplicates
- No logging of credential values

### Pairing Flow Integration

**Happy path verified:**
1. `ContentView` checks `CredentialStore.isPaired` → shows `PairingView` if false
2. User enters server URL → `PairingViewModel.startPairing()` calls `APIClient.requestPairing()`
3. Backend creates `pairing_sessions` row with token + 6-digit PIN, notifies parent via Telegram
4. Frontend displays QR code (token encoded via CoreImage) + PIN digits
5. Frontend polls `getPairStatus(token:)` every `Config.pollInterval` (3s)
6. Parent taps Approve in Telegram → backend calls `confirm_pairing()`, issues device API key, stores key on session via `set_pairing_device_key()`
7. Next poll returns `{status: "confirmed", api_key: "...", server_url: "..."}`
8. Frontend stores credentials via `CredentialStore.store()`, transitions to success → profile picker
9. Subsequent `Config.serverBaseURL` and `Config.apiKey` reads return Keychain values
10. `verify_api_key()` in auth.py accepts the device's issued key

**Expiration/regeneration verified:**
- `startExpirationTimer()` warns at 60s remaining, auto-regenerates on expiry
- Backend status poll returns `"expired"` when `expires_at` has passed
- `handleExpiration()` requests fresh token + PIN automatically

**Denial flow verified:**
- Parent taps Deny → backend sets `status = 'denied'`
- Frontend poll detects `isDenied`, shows denied step with "Try Again" button
- Try Again calls `startPairing()` again for a fresh session

**Unpair flow verified:**
- `ProfileView` shows "Forget Server" destructive button with `wifi.slash` icon
- Calls `CredentialStore.clear()`, resets `selectedChild` and `isPaired` → returns to `PairingView`

### Telegram Bot Integration

**Pairing notification (`notify_pairing_request`):**
- Sends device name, PIN, and expiry to admin chat
- Inline keyboard with Approve/Deny buttons (callback data: `pair_ok:{token}` / `pair_deny:{token}`)

**Callback handling:**
- `pair_ok` → calls `confirm_pairing(token)`, then `set_pairing_device_key(token, api_key)` so status poll can return the key
- `pair_deny` → sets session status to `'denied'`
- Handles edge cases: already paired, session expired/not found

**Device management (`/devices` command):**
- Lists all paired devices with revoke buttons
- Revoke sets `is_active = 0`, effectively invalidating the device's API key

### Data Layer

**`pairing_sessions` table:**
- Fields: id, token (unique), pin, status, device_name, device_api_key, created_at, expires_at, confirmed_at
- `device_api_key` is set post-confirmation so status polling can return it

**`paired_devices` table:**
- Fields: id, device_name, api_key (unique), paired_at, last_seen_at, is_active
- Soft-delete via `is_active = 0` (revoke doesn't remove the row)

**Key methods verified:**
- `create_pairing_session()` — generates `secrets.token_urlsafe(32)` token + 6-digit PIN
- `get_pairing_session_by_pin()` — only returns pending, non-expired sessions
- `confirm_pairing()` — issues `secrets.token_urlsafe(48)` device key, atomic confirm + insert
- `cleanup_expired_pairing_sessions()` — deletes expired pending sessions (called on each new request)

### Rate Limiting

- `POST /api/pair/request` — 10/minute (prevents pairing request spam)
- `POST /api/pair/confirm-by-pin` — 10/minute (mitigates PIN brute force)
- PIN is 6 digits (1M combinations) + 5-minute expiry window = adequate for home use

## Findings

### Finding 1 (Low): `expires_at` not used by frontend

**Backend** returns `expires_at` (ISO datetime string) in `PairRequestResponse`.
**Frontend** `PairRequestResponse` model includes `expiresAt` but the `PairingViewModel` only uses `expiresIn` (integer seconds) for the expiration timer.

**Impact:** None — `expiresIn` is sufficient for the client-side countdown. The `expires_at` field provides a server-canonical timestamp that could be useful for clock-skew resilience but isn't needed for the current implementation.

**Action:** No change required.

### Finding 2 (Low): QR code encodes raw token, not a URL

The QR code is generated from `response.token` directly (a base64url string). Some pairing flows encode a URL (e.g., `https://server/pair?token=xxx`) to allow scanning from a browser.

**Impact:** Low — the Telegram bot approach means QR scanning is secondary. The bot receives approve/deny buttons directly. QR code is a convenience fallback.

**Action:** Consider encoding as a URL in a future iteration if a web-based approval flow is added.

### Finding 3 (Info): Test plans reference old model names

`tvos/Tests/PairingTests.swift` comments reference `PairingSession` and `PairingStatus` model names, but the actual implementations are named `PairRequestResponse` and `PairStatusResponse`.

**Impact:** None — all test code is commented out. When uncommenting, model names will need updating.

**Action:** Update commented test code to use `PairRequestResponse` / `PairStatusResponse` when activating tests.

## Test Results

**Backend:** 34/34 pairing tests pass (pytest)
**Frontend:** 126/126 tests pass (swift test) — pairing tests are documented but commented out (require tvOS SDK for Keychain)
**Full test suite:** `pytest` 646 tests pass (per backend-dev report)

## Verdict

**Ready for merge.** No critical or high-severity integration issues found. All endpoint paths, request/response models, authentication flows, and data layer operations are correctly aligned between frontend and backend. The pairing flow is complete end-to-end:

- First launch → PairingView → server URL entry → QR + PIN → Telegram notification → parent approval → credentials stored → normal app flow
- Expiration auto-regenerates
- Denial shows retry option
- Unpair via "Forget Server" clears Keychain and returns to pairing
- Device keys work for authentication alongside master key
