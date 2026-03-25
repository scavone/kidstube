# Test Plan: Pairing UX Fixes
## Issues: Telegram message update on web approval + Custom device naming

**Date:** 2026-03-25
**Author:** qa-analyst
**Status:** Phase 1 — Baseline established, awaiting dev completion for Phase 2

---

## Scope

Two related fixes to the device pairing flow:

1. **Telegram message update** — When a parent approves or denies a pairing request via the web QR-code approval page (`/api/pair/approve/{token}`), the original Telegram notification message (with Approve/Deny buttons) must be edited to reflect the outcome. Currently the Telegram message stays with live buttons even after web-side resolution.

2. **Custom device naming** — The tvOS app hardcodes `"device_name": "Apple TV"` in `APIClient.requestPairing()`. Parents should be able to assign a meaningful name (e.g., "Living Room TV") either during initial pairing (tvOS input field) or at approval time (web approval page form field). Telegram approval via bot should also support name override.

---

## Current State (Pre-Fix Baseline)

### Known gaps identified in code review:

| Location | Issue |
|---|---|
| `server/bot/telegram_bot.py:369` | `notify_pairing_request()` sends message but does **not** save `message_id` |
| `server/data/video_store.py:152` | `pairing_sessions` table has **no** `telegram_message_id` column |
| `server/api/routes.py:1716` | `pair_approve_web` has **no** callback to edit the Telegram message |
| `server/api/routes.py:1733` | `pair_deny_web` has **no** callback to edit the Telegram message |
| `tvos/Sources/Services/APIClient.swift:318` | `requestPairing()` hardcodes `"Apple TV"` as device name |
| `tvos/Sources/Views/Pairing/PairingView.swift` | No device name input field |
| Web approval HTML (`routes.py:1631`) | No device name input field |
| `server/bot/telegram_bot.py:653` | `pair_deny` Telegram handler uses raw SQL instead of `deny_pairing()` |

---

## Fix 1: Telegram Message Update on Web Approval

### What must change
- `pairing_sessions` table: add `telegram_message_id INTEGER` and `telegram_chat_id INTEGER` columns (via `_migrate()`)
- `notify_pairing_request()`: save `sent_message.message_id` and `chat_id` to the session after `send_message()`
- New bot method (e.g., `update_pairing_message(token, text)`): edit the stored message, removing buttons
- `pair_approve_web` and `pair_deny_web` routes: call a `notify_pairing_update_callback` (similar to `notify_pairing_callback`)

### Test Cases — Backend (pytest)

#### TC-TG-01: Telegram message ID stored after notification
- Create a pairing session
- Simulate `notify_pairing_request()` with a mock bot that returns `message_id=42, chat_id=99`
- Assert `video_store.get_pairing_session(token)["telegram_message_id"] == 42`

#### TC-TG-02: Web approve → Telegram message edited
- Create session, store mock `telegram_message_id`
- Call `POST /api/pair/approve-web/{token}`
- Assert the mock bot's `edit_message_text` was called once with text not containing buttons

#### TC-TG-03: Web deny → Telegram message edited
- Same flow for `POST /api/pair/deny-web/{token}`
- Assert `edit_message_text` called with denial text and no keyboard markup

#### TC-TG-04: Telegram approve still works (regression)
- Create session, call the Telegram `pair_ok` callback handler
- Assert session status is `confirmed` and `_send_or_edit` was called with success text
- Assert `pair_status` returns `confirmed` with `api_key`

#### TC-TG-05: Telegram deny still works (regression)
- Call the Telegram `pair_deny` callback handler
- Assert session status is `denied`
- **Note:** current handler uses raw SQL (`UPDATE ... SET status = 'denied'`) instead of `deny_pairing()` — verify consistency after fix

#### TC-TG-06: No Telegram bot configured — web approval still succeeds silently
- `notify_pairing_update_callback = None`
- Call `pair_approve_web` — assert 200 OK, no exception raised

#### TC-TG-07: Telegram message not found (deleted by user) — web approval still succeeds
- Store a `telegram_message_id` but mock `edit_message_text` to raise `telegram.error.BadRequest("Message to edit not found")`
- Assert `pair_approve_web` still returns 200 (edit failure is non-fatal)

#### TC-TG-08: Race condition — web approve + Telegram approve simultaneously
- Create session
- Telegram approve completes first → status = `confirmed`
- Web approve called next → should return 409 (already paired)
- Assert Telegram message not edited a second time (idempotent)

#### TC-TG-09: Race condition — web deny + Telegram approve simultaneously
- Deny via web first → status = `denied`
- Telegram `pair_ok` called next → `confirm_pairing()` returns None
- Assert bot shows "Already paired" or "Expired" gracefully (not a crash)

#### TC-TG-10: Migration adds columns without breaking existing DB
- Create DB with old schema (no `telegram_message_id` column)
- Run `_migrate()`
- Assert new columns exist with NULL for existing rows
- Assert existing pairing sessions are unaffected

---

## Fix 2: Custom Device Naming

### What must change
- `tvos/Sources/Views/Pairing/PairingView.swift`: Add a device name `TextField` (step 1 or new sub-step)
- `tvos/Sources/Services/APIClient.swift:requestPairing()`: Accept `deviceName: String` parameter, send in request body
- `tvos/Sources/Models/PairingModels.swift`: Optionally include `deviceName` in `PairRequestResponse` (confirmed name)
- Web approval HTML (`/api/pair/approve/{token}`): Add a text input for overriding/setting device name
- `server/api/routes.py:pair_approve_web`: Accept and pass `device_name` to `confirm_pairing()`
- `server/api/routes.py:pair_confirm`: Already accepts `device_name` in `PairConfirmBody` ✓
- `server/api/models.py:PairRequestBody`: Already accepts `device_name` ✓

### Test Cases — Backend (pytest)

#### TC-DN-01: Custom name from tvOS request stored in session
- `POST /api/pair/request` with `{"device_name": "Bedroom TV"}`
- `GET /api/pair/status/{token}` → assert session has `device_name = "Bedroom TV"`
- After confirm: `GET /api/devices` → assert `device_name = "Bedroom TV"`

#### TC-DN-02: Name override at Telegram confirm time
- `POST /api/pair/request` with `{"device_name": "Old Name"}`
- `POST /api/pair/confirm/{token}` with `{"device_name": "New Name"}`
- `GET /api/devices` → assert `device_name = "New Name"` (confirm-time override wins)

#### TC-DN-03: Name override at web approval time
- `POST /api/pair/request` with `{"device_name": "Old Name"}`
- `POST /api/pair/approve-web/{token}` with `{"device_name": "Web Name"}` (new body param)
- `GET /api/devices` → assert `device_name = "Web Name"`

#### TC-DN-04: Empty name falls back to "Apple TV"
- `POST /api/pair/request` with `{}` (no device_name)
- Confirm without device_name override
- `GET /api/devices` → assert `device_name = "Apple TV"`

#### TC-DN-05: Whitespace-only name treated as empty (falls back to "Apple TV")
- `POST /api/pair/request` with `{"device_name": "   "}`
- Confirm → assert `device_name = "Apple TV"` (or server strips whitespace)

#### TC-DN-06: Name from tvOS used when Telegram confirm has no override
- `POST /api/pair/request` with `{"device_name": "Kids Room TV"}`
- `POST /api/pair/confirm/{token}` with no body (no device_name)
- `GET /api/devices` → assert `device_name = "Kids Room TV"` (tvOS name preserved)

#### TC-DN-07: Name length validation
- `POST /api/pair/request` with `{"device_name": "X" * 101}` → assert 422 (max_length=100 in model)
- `POST /api/pair/request` with `{"device_name": "X" * 100}` → assert 200

#### TC-DN-08: /devices Telegram command shows correct name
- Pair a device with name "Living Room TV"
- Call `_cmd_devices` handler → assert message contains "Living Room TV"

### Test Cases — tvOS (Swift Testing)

#### TC-IOS-01: `requestPairing(deviceName:)` sends device_name in body
- Mock `POST /api/pair/request` to capture request body
- Call `apiClient.requestPairing(deviceName: "My TV")`
- Assert request body JSON contains `"device_name": "My TV"`

#### TC-IOS-02: `requestPairing()` without name sends empty or nil device_name
- Call `apiClient.requestPairing(deviceName: "")`
- Assert request body either omits `device_name` or sends `null` (not `"Apple TV"` hardcoded)

#### TC-IOS-03: `PairRequestResponse` decodes correctly with device_name
- Decode JSON with `device_name` field → no crash, optional field handled

#### TC-IOS-04: `PairRequestResponse` decodes correctly without device_name
- Decode JSON without `device_name` field → no crash

### Test Cases — Web Approval Page (manual / integration)

#### TC-WEB-01: Approval page shows device name input
- Load `/api/pair/approve/{token}` in browser
- Assert a text input for device name is visible with placeholder or pre-filled with session's device_name

#### TC-WEB-02: Custom name submitted via web form flows to device record
- Fill device name field → click Approve
- `GET /api/devices` via Telegram `/devices` → assert correct name shown

#### TC-WEB-03: Empty name in web form falls back to session name or "Apple TV"
- Leave device name blank → Approve
- Assert device name is session's original value or "Apple TV", not empty string

---

## Fix 3: Backward Compatibility

#### TC-BC-01: Existing paired devices unaffected by migration
- Pre-populate `paired_devices` table with a device
- Run migration → assert device still listed with correct name and api_key

#### TC-BC-02: Pairing session without `telegram_message_id` (legacy row) doesn't break web approval
- Insert a pairing session row without `telegram_message_id` (NULL)
- Call `pair_approve_web` → assert 200, no KeyError/crash

#### TC-BC-03: Device API key still works for authentication after naming changes
- Confirm pairing with custom name
- Use the returned `api_key` on `GET /api/profiles` → assert 200

#### TC-BC-04: `GET /api/pair/status/{token}` still returns `api_key` after web approval
- Approve via web → poll status → assert `api_key` present and `status = "confirmed"`

---

## Test Execution Plan

### Phase 2 Checklist (after both devs message QA)

**Files to read:**
- `server/data/video_store.py` — confirm `telegram_message_id` column in schema and migration
- `server/bot/telegram_bot.py` — confirm `notify_pairing_request()` saves message ID, new `update_pairing_message()` method
- `server/api/routes.py` — confirm `pair_approve_web` / `pair_deny_web` call new callback, `pair_approve_web` accepts device_name
- `server/api/models.py` — confirm no new model conflicts
- `tvos/Sources/Services/APIClient.swift` — confirm `requestPairing()` accepts/sends device_name
- `tvos/Sources/Views/Pairing/PairingView.swift` — confirm device name input present
- `tvos/Sources/Models/PairingModels.swift` — confirm model updates

**Run server tests:**
```bash
cd server && source .venv/bin/activate && python -m pytest
```

**Run tvOS tests:**
```bash
cd tvos && swift test
```

**Check for conflicts:**
- `server/api/routes.py` — both fixes touch this file (web approval routes)
- `server/bot/telegram_bot.py` — both fixes may touch `notify_pairing_request()`
- `server/data/video_store.py` — migration changes

**Key contract checks:**
- `POST /api/pair/approve-web/{token}` request body: does frontend send JSON? Does server parse `device_name` from body?
- Telegram callback structure: does `notify_pairing_update_callback` signature match what `routes.py` expects?
- DB migration: does adding `telegram_message_id` column run cleanly on existing DB (ALTER TABLE vs CREATE TABLE)?

---

## Risk Areas

| Risk | Severity | Notes |
|---|---|---|
| Telegram `edit_message_text` fails silently if message was deleted | Low | Must not block web approval |
| Race condition: web + Telegram approve simultaneously | Medium | `confirm_pairing()` uses a lock — verify second call returns None gracefully |
| `pair_deny` Telegram handler uses raw SQL, inconsistent with `deny_pairing()` | Low | Pre-existing, but may cause test failures if fix normalizes the code path |
| `pair_approve_web` body parsing — currently has no body model | Medium | Adding `device_name` requires a Pydantic body model; existing callers (browser form POST) may send form-encoded vs JSON |
| tvOS `requestPairing()` currently sends JSON; if signature changes, callers must update | Low | `PairingViewModel.startPairing()` and `handleExpiration()` both call it |
| Device name field in tvOS — tvOS text input on Apple TV uses on-screen keyboard, which may need UX consideration | Low | Functional correctness only in test scope |
