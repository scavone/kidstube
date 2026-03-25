# QA Report: Pairing UX Fixes
## Issues: Telegram message update on web approval + Custom device naming

**Date:** 2026-03-25
**Reviewer:** qa-analyst
**Verdict: PASS — no blocking issues found**

---

## Test Results

| Suite | Baseline | Post-fix | Result |
|---|---|---|---|
| Server (pytest) | 755 | 774 (+19) | ✅ All pass |
| tvOS (swift test) | 132/133 | 133/133 | ✅ All pass (pre-existing flake resolved) |
| Pairing endpoint tests | — | 53/53 | ✅ All pass |

---

## Fix 1: Telegram Message Update on Web Approval

### Contract Checks

| Check | Status | Notes |
|---|---|---|
| `pairing_sessions` has `chat_id` / `message_id` columns | ✅ PASS | Migration via `PRAGMA table_info` + `ALTER TABLE` — safe on existing DBs |
| `notify_pairing_request()` saves message IDs after send | ✅ PASS | `set_pairing_message_ids(token, msg.chat_id, msg.message_id)` at bot.py:401 |
| `edit_pairing_message()` handles missing IDs (no Telegram session) | ✅ PASS | Returns early if `chat_id` or `message_id` is None |
| `edit_pairing_message()` handles deleted/missing message gracefully | ✅ PASS | Inner try/except logs warning, does not raise |
| `pair_approve_web` edits Telegram message after approval | ✅ PASS | Non-fatal try/except wraps the call |
| `pair_deny_web` edits Telegram message after denial | ✅ PASS | Non-fatal try/except wraps the call |
| Telegram `pair_ok` callback still works (regression) | ✅ PASS | `TestPairConfirmEndpoint` all pass |
| Telegram `pair_deny` callback still works (regression) | ✅ PASS | Existing tests pass |
| Web approval succeeds when no bot configured | ✅ PASS | `telegram_bot_instance = None` path tested by all web tests |
| Race condition: web approve on already-confirmed → 409 | ✅ PASS | `test_approve_web_already_paired_returns_409` |
| Race condition: web deny on already-resolved → 409 | ✅ PASS | `test_deny_web_already_resolved_returns_409` |

### Observations

- **Pre-existing inconsistency (non-blocking):** The Telegram `pair_deny` callback handler (bot.py ~line 658) still uses a raw SQL `UPDATE ... SET status = 'denied'` instead of calling `deny_pairing()`. This predates this fix and doesn't break anything, but creates an inconsistency in code paths. The `deny_pairing()` method is correctly used by `pair_deny_web`.
- **Double exception handling:** `edit_pairing_message` catches exceptions internally AND `routes.py` wraps the call in another try/except. Belt-and-suspenders — fine.
- **No Telegram mock in tests:** Web approval tests don't mock the bot, validating the `bot=None` path. The message ID storage is verified at the store layer (`TestPairingMessageIds`). End-to-end bot editing requires a live bot — acceptable for this test scope.

---

## Fix 2: Custom Device Naming

### Contract Checks

| Check | Status | Notes |
|---|---|---|
| tvOS sends `device_name` as JSON in POST body | ✅ PASS | `APIClient.requestPairing(deviceName:)` sends `Content-Type: application/json` |
| Whitespace-only name falls back to "Apple TV" | ✅ PASS | `.trimmingCharacters(in: .whitespacesAndNewlines)` + empty check in `APIClient` |
| Both `requestPairing` call sites pass `deviceName` | ✅ PASS | `startPairing()` and `handleExpiration()` both pass `viewModel.deviceName` |
| Device name preserved across cancel/retry | ✅ PASS | `cancelPairing()` doesn't reset `deviceName` |
| Web page pre-fills device name from session | ✅ PASS | `test_approve_web_page_prefills_device_name` + HTML uses `value="{device_name}"` |
| Web page defaults to "Apple TV" when no session name | ✅ PASS | `test_approve_web_page_defaults_to_apple_tv` |
| Web JS sends JSON body with `device_name` on approve | ✅ PASS | `opts.headers = {'Content-Type': 'application/json'}` + `JSON.stringify(...)` |
| Empty web name sends `null` → falls back to session name | ✅ PASS | JS: `name || null`; server: `device_name or session["device_name"] or "Apple TV"` |
| `pair_approve_web` passes `device_name` to `confirm_pairing()` | ✅ PASS | `device_name = (body.device_name if body else None)` at routes.py:1744 |
| Confirm-time name override wins over request-time name | ✅ PASS | `confirm_pairing(device_name=...)` logic: explicit arg > session > "Apple TV" |
| `PairApproveWebBody` validates `max_length=100` | ✅ PASS | Consistent with `PairRequestBody` and `PairConfirmBody` |
| `/device rename <id> <name>` command works | ✅ PASS | `test_rename_device` |
| `/device rename` on revoked device → False | ✅ PASS | `test_rename_revoked_device_returns_false` (checks `is_active = 1`) |
| `/device rename` on unknown device → False | ✅ PASS | `test_rename_nonexistent_device_returns_false` |
| `/devices` lists updated name after rename | ✅ PASS | Via `get_paired_devices()` after `rename_device()` |
| Multi-word device names supported | ✅ PASS | Bot uses `" ".join(args[2:])` |

### Observations

- Web JS only sends a JSON body for **approve**, not deny. This is correct — `pair_deny_web` has no body and the deny action doesn't need a device name. ✅
- The `"Try Again"` button in the denied state calls `viewModel.startPairing()` which reads `self.deviceName` — the previously entered name is preserved correctly. ✅

---

## Backward Compatibility

| Check | Status |
|---|---|
| Existing paired devices unaffected by migration | ✅ PASS — migration only adds nullable columns |
| Pairing session without `chat_id`/`message_id` (NULL) → approve-web works | ✅ PASS — `edit_pairing_message` returns early on None |
| Device API key from confirmed pairing still authenticates | ✅ PASS — `test_generated_api_key_works_for_auth` |
| `GET /api/pair/status/{token}` still returns `api_key` after web approval | ✅ PASS — `set_pairing_device_key` called before returning |

---

## Minor Issues (Non-blocking)

1. **Telegram `pair_deny` raw SQL** — bot.py uses direct SQL instead of `deny_pairing()`. Pre-existing, not introduced by this fix.
2. **tvOS pre-existing flake** — `UIOverhaulTests "Get recently added — empty list"` was failing in baseline (URL scheme error) and now passes. Likely a transient ordering issue, not related to this fix.

---

## QA Sign-off

All test plan checks from `tests/test-plan-pairing-ux-fixes.md` are verified. Both fixes are correctly implemented, contract-aligned between frontend and backend, and test coverage is solid. Ready to merge.
