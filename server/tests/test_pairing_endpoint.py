"""Test plan for Issue #8: QR code / pin code pairing endpoints.

Replaces hardcoded server credentials with a device pairing flow.
TV app displays a QR code and PIN, parent confirms via admin interface,
TV app receives and stores credentials.

Expected endpoints:
  POST /api/pair/request        — TV app initiates pairing, gets token + PIN + QR data
  GET  /api/pair/status/{token} — TV app polls for confirmation (no auth required)
  POST /api/pair/confirm/{token} — Admin confirms pairing, returns long-lived API key

Expected DB: pairing_sessions table with token, pin, status, device_name, created_at, expires_at, api_key
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import time
from unittest.mock import patch
from fastapi.testclient import TestClient

from config import Config
from data.video_store import VideoStore
from invidious.client import InvidiousClient
from main import create_app
from api import routes as api_routes


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def cfg():
    return Config(
        app_name="TestApp",
        api_key="test-secret-key",
        watch_limits=Config.__dataclass_fields__["watch_limits"].default_factory(),
    )


@pytest.fixture
def store(tmp_path):
    s = VideoStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def mock_invidious():
    return InvidiousClient(base_url="http://test:3000")


@pytest.fixture
def app(cfg, store, mock_invidious):
    from fastapi import FastAPI
    app = FastAPI(title="Test")
    app.state.api_key = cfg.api_key
    api_routes.setup(store, mock_invidious, cfg)
    app.include_router(api_routes.router)
    app.include_router(api_routes.public_router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-secret-key"}


# ── POST /api/pair/request — Initiate Pairing ───────────────────

class TestPairRequestEndpoint:
    """TV app calls this to start a pairing session."""

    def test_creates_pairing_session(self, client):
        """Returns a token, PIN, and QR code data."""
        resp = client.post("/api/pair/request")
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "pin" in data
        assert "expires_in" in data

    def test_token_is_unique(self, client):
        """Each request generates a unique token."""
        resp1 = client.post("/api/pair/request")
        resp2 = client.post("/api/pair/request")
        assert resp1.json()["token"] != resp2.json()["token"]

    def test_pin_is_6_digits(self, client):
        """PIN is a 6-digit numeric string."""
        resp = client.post("/api/pair/request")
        pin = resp.json()["pin"]
        assert len(pin) == 6
        assert pin.isdigit()

    def test_token_format(self, client):
        """Token should be a URL-safe string of reasonable length."""
        resp = client.post("/api/pair/request")
        token = resp.json()["token"]
        assert len(token) >= 16  # sufficient entropy
        # URL-safe characters only
        import re
        assert re.match(r'^[a-zA-Z0-9_-]+$', token)

    def test_expires_in_is_reasonable(self, client):
        """Expires in ~5 minutes (300 seconds)."""
        resp = client.post("/api/pair/request")
        expires_in = resp.json()["expires_in"]
        assert 240 <= expires_in <= 360  # ~5 minutes with some tolerance

    def test_no_auth_required(self, client):
        """Pairing request does not require an existing API key.
        The whole point is that the TV doesn't have one yet."""
        resp = client.post("/api/pair/request")
        assert resp.status_code == 200

    def test_optional_device_name(self, client):
        """Can pass an optional device_name for identification."""
        resp = client.post("/api/pair/request", json={"device_name": "Living Room TV"})
        assert resp.status_code == 200

    def test_rate_limiting(self, client):
        """Should rate-limit pairing requests to prevent abuse."""
        # Rapid-fire requests from same IP
        for _ in range(20):
            client.post("/api/pair/request")
        resp = client.post("/api/pair/request")
        assert resp.status_code == 429  # Too Many Requests


# ── GET /api/pair/status/{token} — Poll Pairing Status ──────────

class TestPairStatusEndpoint:
    """TV app polls this to check if the parent confirmed pairing."""

    def test_pending_status(self, client):
        """Newly created pairing shows 'pending' status."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        resp = client.get(f"/api/pair/status/{token}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_no_auth_required(self, client):
        """Status polling does not require auth (TV doesn't have a key yet)."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]
        # No auth headers — should still work
        resp = client.get(f"/api/pair/status/{token}")
        assert resp.status_code == 200

    def test_invalid_token_returns_404(self, client):
        """Unknown token returns 404."""
        resp = client.get("/api/pair/status/nonexistent-token-12345")
        assert resp.status_code == 404

    def test_confirmed_status_includes_credentials(self, client, auth_headers):
        """After confirmation, status includes server_url and api_key."""
        # Create pairing
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        # Confirm (admin action)
        client.post(f"/api/pair/confirm/{token}", headers=auth_headers)

        # Poll — should now be confirmed with credentials
        resp = client.get(f"/api/pair/status/{token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"
        assert "api_key" in data
        assert len(data["api_key"]) >= 32  # strong key

    def test_expired_token_returns_expired(self, client):
        """Expired pairing session shows 'expired' status."""
        # This test needs the pairing to be created with a very short expiry,
        # or we mock time. Implementation will determine exact approach.
        pass

    def test_credentials_only_returned_once(self, client, auth_headers):
        """After first successful status poll with credentials, subsequent
        polls should still show confirmed but may omit the raw api_key
        for security (implementation choice — document behavior)."""
        pass


# ── POST /api/pair/confirm/{token} — Admin Confirms Pairing ─────

class TestPairConfirmEndpoint:
    """Admin interface calls this to approve a pairing request."""

    def test_confirm_requires_auth(self, client):
        """Confirmation requires admin auth (existing API key)."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        resp = client.post(f"/api/pair/confirm/{token}")
        assert resp.status_code == 401

    def test_confirm_with_wrong_key(self, client):
        """Wrong API key is rejected."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        resp = client.post(
            f"/api/pair/confirm/{token}",
            headers={"Authorization": "Bearer wrong-key"}
        )
        assert resp.status_code == 401

    def test_confirm_success(self, client, auth_headers):
        """Confirming a valid pending pairing succeeds."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        resp = client.post(f"/api/pair/confirm/{token}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"
        assert "api_key" in data

    def test_confirm_by_pin(self, client, auth_headers):
        """Can confirm pairing using the PIN instead of the token."""
        create_resp = client.post("/api/pair/request")
        pin = create_resp.json()["pin"]

        resp = client.post(
            "/api/pair/confirm-by-pin",
            json={"pin": pin},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

    def test_confirm_invalid_token_returns_404(self, client, auth_headers):
        """Confirming a nonexistent token returns 404."""
        resp = client.post(
            "/api/pair/confirm/nonexistent-token",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_confirm_expired_token_returns_410(self, client, auth_headers):
        """Confirming an expired token returns 410 Gone."""
        pass

    def test_confirm_already_confirmed_returns_409(self, client, auth_headers):
        """Confirming an already-confirmed pairing returns 409 Conflict."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        # First confirm
        client.post(f"/api/pair/confirm/{token}", headers=auth_headers)
        # Second confirm
        resp = client.post(f"/api/pair/confirm/{token}", headers=auth_headers)
        assert resp.status_code == 409

    def test_generated_api_key_is_unique(self, client, auth_headers):
        """Each confirmed pairing generates a unique API key."""
        r1 = client.post("/api/pair/request")
        r2 = client.post("/api/pair/request")
        t1, t2 = r1.json()["token"], r2.json()["token"]

        c1 = client.post(f"/api/pair/confirm/{t1}", headers=auth_headers)
        c2 = client.post(f"/api/pair/confirm/{t2}", headers=auth_headers)
        assert c1.json()["api_key"] != c2.json()["api_key"]

    def test_generated_api_key_works_for_auth(self, client, auth_headers):
        """The generated API key can be used for subsequent API calls."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        confirm_resp = client.post(f"/api/pair/confirm/{token}", headers=auth_headers)
        new_key = confirm_resp.json()["api_key"]

        # Use the new key to call an authenticated endpoint
        resp = client.get(
            "/api/profiles",
            headers={"Authorization": f"Bearer {new_key}"},
        )
        assert resp.status_code == 200


# ── Security ─────────────────────────────────────────────────────

class TestPairingSecurity:
    """Security-focused tests for the pairing flow."""

    def test_pin_not_reusable(self, client, auth_headers):
        """After a PIN is used to confirm, it cannot be used again."""
        create_resp = client.post("/api/pair/request")
        pin = create_resp.json()["pin"]

        # Confirm with PIN
        client.post("/api/pair/confirm-by-pin", json={"pin": pin}, headers=auth_headers)

        # Try again with same PIN
        resp = client.post("/api/pair/confirm-by-pin", json={"pin": pin}, headers=auth_headers)
        assert resp.status_code in (404, 409)  # not found or conflict

    def test_pin_brute_force_protection(self, client, auth_headers):
        """Rate limit PIN confirmation attempts to prevent brute force."""
        # Try many wrong PINs rapidly
        for _ in range(20):
            client.post(
                "/api/pair/confirm-by-pin",
                json={"pin": "000000"},
                headers=auth_headers,
            )
        resp = client.post(
            "/api/pair/confirm-by-pin",
            json={"pin": "000000"},
            headers=auth_headers,
        )
        assert resp.status_code == 429

    def test_token_not_guessable(self, client):
        """Tokens should have sufficient entropy (at least 128 bits)."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]
        # URL-safe base64: each char is ~6 bits, so 22+ chars for 128 bits
        assert len(token) >= 22

    def test_api_key_not_in_status_before_confirm(self, client):
        """Status endpoint does not leak credentials before confirmation."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        resp = client.get(f"/api/pair/status/{token}")
        data = resp.json()
        assert "api_key" not in data or data.get("api_key") is None

    def test_expired_sessions_cleaned_up(self, client):
        """Expired pairing sessions should be cleaned up (not accumulate)."""
        # Implementation detail — verify old sessions don't persist indefinitely
        pass


# ── PIN Validation ───────────────────────────────────────────────

class TestPinValidation:
    """PIN format and uniqueness constraints."""

    def test_pin_collision_avoidance(self, client):
        """Active PINs should not collide (unique among pending sessions)."""
        pins = set()
        for _ in range(10):
            resp = client.post("/api/pair/request")
            pins.add(resp.json()["pin"])
        # All PINs should be unique (10 out of 1M possible — vanishingly unlikely collision)
        assert len(pins) == 10

    def test_confirm_wrong_pin_returns_404(self, client, auth_headers):
        """Wrong PIN returns 404."""
        client.post("/api/pair/request")  # create a session
        resp = client.post(
            "/api/pair/confirm-by-pin",
            json={"pin": "000000"},
            headers=auth_headers,
        )
        # Should be 404 unless 000000 happens to match (extremely unlikely)
        assert resp.status_code in (404, 200)


# ── Device Management ────────────────────────────────────────────

class TestDeviceManagement:
    """Admin can list and revoke paired devices."""

    def test_list_paired_devices(self, client, auth_headers):
        """GET /api/devices returns list of paired devices."""
        # Create and confirm a pairing
        create_resp = client.post("/api/pair/request", json={"device_name": "Living Room TV"})
        token = create_resp.json()["token"]
        client.post(f"/api/pair/confirm/{token}", headers=auth_headers)

        resp = client.get("/api/devices", headers=auth_headers)
        assert resp.status_code == 200
        devices = resp.json()["devices"]
        assert len(devices) >= 1
        assert any(d["device_name"] == "Living Room TV" for d in devices)

    def test_revoke_device(self, client, auth_headers):
        """DELETE /api/devices/{device_id} revokes a paired device."""
        # Create and confirm
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]
        confirm_resp = client.post(f"/api/pair/confirm/{token}", headers=auth_headers)
        device_key = confirm_resp.json()["api_key"]

        # List devices to get the device ID
        devices_resp = client.get("/api/devices", headers=auth_headers)
        device_id = devices_resp.json()["devices"][0]["id"]

        # Revoke
        resp = client.delete(f"/api/devices/{device_id}", headers=auth_headers)
        assert resp.status_code == 200

        # Verify the revoked key no longer works
        resp = client.get(
            "/api/profiles",
            headers={"Authorization": f"Bearer {device_key}"},
        )
        assert resp.status_code == 401

    def test_list_devices_requires_auth(self, client):
        """Device listing requires auth."""
        resp = client.get("/api/devices")
        assert resp.status_code == 401

    def test_revoke_requires_auth(self, client):
        """Device revocation requires auth."""
        resp = client.delete("/api/devices/1")
        assert resp.status_code == 401


# ── Web Approval Flow ─────────────────────────────────────────────

class TestWebApprovalFlow:
    """Tests for QR-code web approval page and API endpoints."""

    def test_approve_web_page_renders(self, client):
        """GET /api/pair/approve/{token} returns the HTML approval page."""
        create_resp = client.post("/api/pair/request", json={"device_name": "Bedroom TV"})
        token = create_resp.json()["token"]

        resp = client.get(f"/api/pair/approve/{token}")
        assert resp.status_code == 200
        assert "Bedroom TV" in resp.text
        assert 'id="device_name"' in resp.text  # device name input present

    def test_approve_web_page_prefills_device_name(self, client):
        """The web page pre-fills the device name input from the session."""
        create_resp = client.post("/api/pair/request", json={"device_name": "Living Room"})
        token = create_resp.json()["token"]

        resp = client.get(f"/api/pair/approve/{token}")
        assert "Living Room" in resp.text

    def test_approve_web_page_defaults_to_apple_tv(self, client):
        """When no device_name is provided, the input defaults to 'Apple TV'."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        resp = client.get(f"/api/pair/approve/{token}")
        assert "Apple TV" in resp.text

    def test_approve_web_without_body(self, client):
        """POST /api/pair/approve-web/{token} works without a body (uses session name)."""
        create_resp = client.post("/api/pair/request", json={"device_name": "Original Name"})
        token = create_resp.json()["token"]

        resp = client.post(f"/api/pair/approve-web/{token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"
        assert data["device_name"] == "Original Name"

    def test_approve_web_with_device_name(self, client):
        """POST /api/pair/approve-web/{token} accepts device_name override."""
        create_resp = client.post("/api/pair/request", json={"device_name": "Apple TV"})
        token = create_resp.json()["token"]

        resp = client.post(
            f"/api/pair/approve-web/{token}",
            json={"device_name": "Bedroom TV"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"
        assert data["device_name"] == "Bedroom TV"

    def test_approve_web_device_name_persisted(self, client, store, auth_headers):
        """Device name override from web approval is stored in paired_devices."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        client.post(
            f"/api/pair/approve-web/{token}",
            json={"device_name": "Kitchen TV"},
        )

        devices = store.get_paired_devices()
        assert any(d["device_name"] == "Kitchen TV" for d in devices)

    def test_approve_web_null_device_name_uses_session(self, client):
        """Sending device_name: null falls back to the session's device name."""
        create_resp = client.post("/api/pair/request", json={"device_name": "Session Name"})
        token = create_resp.json()["token"]

        resp = client.post(
            f"/api/pair/approve-web/{token}",
            json={"device_name": None},
        )
        assert resp.status_code == 200
        assert resp.json()["device_name"] == "Session Name"

    def test_approve_web_already_paired_returns_409(self, client):
        """Approving an already-confirmed session returns 409."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        client.post(f"/api/pair/approve-web/{token}")
        resp = client.post(f"/api/pair/approve-web/{token}")
        assert resp.status_code == 409

    def test_approve_web_unknown_token_returns_404(self, client):
        """Unknown token returns 404."""
        resp = client.post("/api/pair/approve-web/nonexistent-token")
        assert resp.status_code == 404

    def test_deny_web(self, client):
        """POST /api/pair/deny-web/{token} denies the session."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        resp = client.post(f"/api/pair/deny-web/{token}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "denied"

    def test_deny_web_updates_status(self, client, store):
        """After denial, the session status is 'denied' in DB."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        client.post(f"/api/pair/deny-web/{token}")

        session = store.get_pairing_session(token)
        assert session["status"] == "denied"

    def test_deny_web_already_resolved_returns_409(self, client):
        """Denying an already-resolved session returns 409."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]

        client.post(f"/api/pair/deny-web/{token}")
        resp = client.post(f"/api/pair/deny-web/{token}")
        assert resp.status_code == 409

    def test_deny_web_unknown_token_returns_404(self, client):
        """Unknown token returns 404."""
        resp = client.post("/api/pair/deny-web/nonexistent-token")
        assert resp.status_code == 404


# ── Pairing Message ID Storage ────────────────────────────────────

class TestPairingMessageIds:
    """Tests for Telegram message ID storage on pairing sessions."""

    def test_set_and_get_pairing_message_ids(self, store):
        """set_pairing_message_ids stores chat_id and message_id on the session."""
        session = store.create_pairing_session(device_name="Test TV")
        token = session["token"]

        store.set_pairing_message_ids(token, chat_id=12345, message_id=67890)

        retrieved = store.get_pairing_session(token)
        assert retrieved["chat_id"] == 12345
        assert retrieved["message_id"] == 67890

    def test_message_ids_default_null(self, store):
        """Newly created pairing sessions have null chat_id and message_id."""
        session = store.create_pairing_session()
        token = session["token"]

        retrieved = store.get_pairing_session(token)
        assert retrieved.get("chat_id") is None
        assert retrieved.get("message_id") is None

    def test_set_message_ids_unknown_token(self, store):
        """Setting message IDs for an unknown token is a no-op (no error)."""
        store.set_pairing_message_ids("nonexistent", chat_id=1, message_id=2)  # should not raise


# ── Device Renaming ───────────────────────────────────────────────

class TestDeviceRenaming:
    """Tests for renaming paired devices."""

    def test_rename_device(self, client, store, auth_headers):
        """rename_device updates the device name."""
        create_resp = client.post("/api/pair/request", json={"device_name": "Old Name"})
        token = create_resp.json()["token"]
        client.post(f"/api/pair/confirm/{token}", headers=auth_headers)

        devices = store.get_paired_devices()
        device_id = devices[0]["id"]

        result = store.rename_device(device_id, "New Name")
        assert result is True

        devices = store.get_paired_devices()
        assert devices[0]["device_name"] == "New Name"

    def test_rename_nonexistent_device_returns_false(self, store):
        """rename_device returns False for unknown device IDs."""
        result = store.rename_device(9999, "Any Name")
        assert result is False

    def test_rename_revoked_device_returns_false(self, client, store, auth_headers):
        """rename_device returns False for already-revoked devices."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]
        client.post(f"/api/pair/confirm/{token}", headers=auth_headers)

        devices = store.get_paired_devices()
        device_id = devices[0]["id"]

        store.revoke_device(device_id)
        result = store.rename_device(device_id, "New Name")
        assert result is False
