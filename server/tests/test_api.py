"""Tests for the API layer — auth, routes, and full request/response cycle.

Uses FastAPI TestClient with a mocked Invidious client.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from config import Config
from data.video_store import VideoStore
from invidious.client import InvidiousClient
from main import create_app
from api import routes as api_routes


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
    client = InvidiousClient(base_url="http://test:3000")
    return client


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


class TestAuth:
    def test_missing_auth_returns_401(self, client):
        resp = client.get("/api/profiles")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client):
        resp = client.get("/api/profiles", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 401

    def test_malformed_header_returns_401(self, client):
        resp = client.get("/api/profiles", headers={"Authorization": "NotBearer key"})
        assert resp.status_code == 401

    def test_valid_key_succeeds(self, client, auth_headers):
        resp = client.get("/api/profiles", headers=auth_headers)
        assert resp.status_code == 200

    def test_no_key_configured_allows_all(self, store, mock_invidious):
        """When no API key is set, auth is skipped (dev mode)."""
        no_key_cfg = Config(app_name="Test", api_key="")
        from fastapi import FastAPI
        app = FastAPI()
        app.state.api_key = ""
        api_routes.setup(store, mock_invidious, no_key_cfg)
        app.include_router(api_routes.router)
        app.include_router(api_routes.public_router)
        c = TestClient(app)
        resp = c.get("/api/profiles")
        assert resp.status_code == 200


class TestProfilesEndpoint:
    def test_list_empty(self, client, auth_headers):
        resp = client.get("/api/profiles", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["profiles"] == []

    def test_create_profile(self, client, auth_headers):
        resp = client.post(
            "/api/profiles",
            json={"name": "Alex", "avatar": "👧"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Alex"
        assert data["avatar"] == "👧"
        assert "id" in data

    def test_create_duplicate_returns_409(self, client, auth_headers):
        client.post("/api/profiles", json={"name": "Alex"}, headers=auth_headers)
        resp = client.post("/api/profiles", json={"name": "Alex"}, headers=auth_headers)
        assert resp.status_code == 409

    def test_list_after_create(self, client, auth_headers):
        client.post("/api/profiles", json={"name": "Alex"}, headers=auth_headers)
        client.post("/api/profiles", json={"name": "Sam"}, headers=auth_headers)
        resp = client.get("/api/profiles", headers=auth_headers)
        assert len(resp.json()["profiles"]) == 2


class TestUpdateProfileEndpoint:
    def test_update_name(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.put(
            "/api/profiles/1",
            json={"name": "Alexander"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Alexander"

    def test_update_avatar(self, client, auth_headers, store):
        store.add_child("Alex", "👦")
        resp = client.put(
            "/api/profiles/1",
            json={"avatar": "👧"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["avatar"] == "👧"

    def test_update_not_found(self, client, auth_headers):
        resp = client.put(
            "/api/profiles/999",
            json={"name": "Ghost"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_update_name_conflict(self, client, auth_headers, store):
        store.add_child("Alex")
        store.add_child("Sam")
        resp = client.put(
            "/api/profiles/2",
            json={"name": "Alex"},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    def test_update_no_fields(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.put(
            "/api/profiles/1",
            json={},
            headers=auth_headers,
        )
        assert resp.status_code == 400


class TestDeleteProfileEndpoint:
    def test_delete_profile(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.delete("/api/profiles/1", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        # Verify child is gone
        assert store.get_child(1) is None

    def test_delete_not_found(self, client, auth_headers):
        resp = client.delete("/api/profiles/999", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_cascades(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")
        store.add_video("vid1", "Title", "Ch")
        store.request_video(child["id"], "vid1")

        resp = client.delete(f"/api/profiles/{child['id']}", headers=auth_headers)
        assert resp.status_code == 200
        # Settings and access should be gone
        assert store.get_child_setting(child["id"], "daily_limit_minutes") == ""
        assert store.get_video_status(child["id"], "vid1") is None


class TestAvatarEndpoints:
    def test_upload_avatar(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.post(
            "/api/profiles/1/avatar",
            files={"file": ("photo.jpg", b"\x89PNG fake image", "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "uploaded"

    def test_get_avatar(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.save_avatar(child["id"], b"\x89PNG fake image data")

        resp = client.get(f"/api/profiles/{child['id']}/avatar", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.content == b"\x89PNG fake image data"

    def test_get_avatar_not_found(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get("/api/profiles/1/avatar", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_avatar_no_auth_required(self, client, store):
        """Avatar GET is public — no auth headers needed."""
        child = store.add_child("Alex")
        store.save_avatar(child["id"], b"\x89PNG image")
        resp = client.get(f"/api/profiles/{child['id']}/avatar")
        assert resp.status_code == 200

    def test_upload_avatar_child_not_found(self, client, auth_headers):
        resp = client.post(
            "/api/profiles/999/avatar",
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestSearchEndpoint:
    def test_search_requires_child_id(self, client, auth_headers):
        resp = client.get("/api/search?q=test", headers=auth_headers)
        assert resp.status_code == 422  # Missing required param

    def test_search_invalid_child(self, client, auth_headers):
        resp = client.get("/api/search?q=test&child_id=999", headers=auth_headers)
        assert resp.status_code == 404

    def test_search_calls_invidious(self, client, auth_headers, store, mock_invidious):
        store.add_child("Alex")

        mock_results = [
            {"video_id": "vid1", "title": "Result", "channel_name": "Ch", "channel_id": "UC1",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0}
        ]

        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results):
            resp = client.get("/api/search?q=test&child_id=1", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["video_id"] == "vid1"

    def test_search_filters_blocked_channels(self, client, auth_headers, store, mock_invidious):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Bad Channel", "blocked")

        mock_results = [
            {"video_id": "v1", "title": "Good", "channel_name": "Good Ch", "channel_id": "UC1",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0},
            {"video_id": "v2", "title": "Bad", "channel_name": "Bad Channel", "channel_id": "UC2",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0},
        ]

        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results):
            resp = client.get("/api/search?q=test&child_id=1", headers=auth_headers)

        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["video_id"] == "v1"

    def test_search_filters_blocked_words(self, client, auth_headers, store, mock_invidious):
        store.add_child("Alex")
        store.add_word_filter("badword")

        mock_results = [
            {"video_id": "v1", "title": "Contains badword here", "channel_name": "Ch", "channel_id": "UC1",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0},
            {"video_id": "v2", "title": "Clean title", "channel_name": "Ch", "channel_id": "UC2",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0},
        ]

        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results):
            resp = client.get("/api/search?q=test&child_id=1", headers=auth_headers)

        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["video_id"] == "v2"


class TestRequestEndpoint:
    def test_request_new_video(self, client, auth_headers, store, mock_invidious):
        store.add_child("Alex")

        mock_video = {
            "video_id": "abc12345678",
            "title": "Test Video",
            "channel_name": "Test Channel",
            "channel_id": "UCTEST",
            "thumbnail_url": "http://thumb.jpg",
            "duration": 300,
            "published": 0,
            "view_count": 0,
            "format_streams": [],
        }

        with patch.object(mock_invidious, "get_video", new_callable=AsyncMock, return_value=mock_video):
            resp = client.post(
                "/api/request",
                json={"video_id": "abc12345678", "child_id": 1},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"

    def test_request_auto_approves_allowed_channel(self, client, auth_headers, store, mock_invidious):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Trusted Channel", "allowed")
        store.add_video("abc12345678", "Video", "Trusted Channel")

        resp = client.post(
            "/api/request",
            json={"video_id": "abc12345678", "child_id": 1},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_request_invalid_video_id(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.post(
            "/api/request",
            json={"video_id": "too-short", "child_id": 1},
            headers=auth_headers,
        )
        assert resp.status_code == 400


class TestStatusEndpoint:
    def test_status_pending(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")

        resp = client.get("/api/status/abc12345678?child_id=1", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_status_not_found(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get("/api/status/abc12345678?child_id=1", headers=auth_headers)
        assert resp.json()["status"] == "not_found"


class TestStreamEndpoint:
    def test_stream_approved_video(self, client, auth_headers, store, mock_invidious):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")
        store.update_video_status(child["id"], "abc12345678", "approved")

        mock_video = {
            "video_id": "abc12345678",
            "title": "Title",
            "channel_name": "Channel",
            "format_streams": [
                {"type": "video/mp4", "url": "http://test/stream.mp4", "qualityLabel": "360p"}
            ],
            "adaptive_formats": [],
            "hls_url": None,
        }
        with patch.object(
            mock_invidious, "get_video",
            new_callable=AsyncMock,
            return_value=mock_video,
        ):
            resp = client.get("/api/stream/abc12345678?child_id=1", headers=auth_headers)

        assert resp.status_code == 200
        assert "url" in resp.json()

    def test_stream_unapproved_returns_403(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")

        resp = client.get("/api/stream/abc12345678?child_id=1", headers=auth_headers)
        assert resp.status_code == 403


class TestCatalogEndpoint:
    def test_catalog_empty(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get("/api/catalog?child_id=1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["videos"] == []
        assert data["total"] == 0

    def test_catalog_with_approved_videos(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Video 1", "Channel")
        store.add_video("vid2", "Video 2", "Channel")
        store.request_video(child["id"], "vid1")
        store.request_video(child["id"], "vid2")
        store.update_video_status(child["id"], "vid1", "approved")
        store.update_video_status(child["id"], "vid2", "approved")

        resp = client.get("/api/catalog?child_id=1", headers=auth_headers)
        data = resp.json()
        assert data["total"] == 2
        assert len(data["videos"]) == 2

    def test_catalog_pagination(self, client, auth_headers, store):
        child = store.add_child("Alex")
        for i in range(5):
            vid = f"video{i:07d}"
            store.add_video(vid, f"Video {i}", "Channel")
            store.request_video(child["id"], vid)
            store.update_video_status(child["id"], vid, "approved")

        resp = client.get("/api/catalog?child_id=1&offset=0&limit=2", headers=auth_headers)
        data = resp.json()
        assert len(data["videos"]) == 2
        assert data["has_more"] is True
        assert data["total"] == 5


class TestHeartbeatEndpoint:
    def test_heartbeat_records_seconds(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")
        store.update_video_status(child["id"], "abc12345678", "approved")

        resp = client.post(
            "/api/watch-heartbeat",
            json={"video_id": "abc12345678", "child_id": 1, "seconds": 30},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert "remaining" in resp.json()

    def test_heartbeat_unapproved_returns_400(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")

        resp = client.post(
            "/api/watch-heartbeat",
            json={"video_id": "abc12345678", "child_id": 1, "seconds": 30},
            headers=auth_headers,
        )
        assert resp.status_code == 400


class TestTimeStatusEndpoint:
    def test_time_status(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")

        resp = client.get("/api/time-status?child_id=1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit_min"] == 60
        assert data["used_min"] == 0
        assert data["remaining_min"] == 60.0
        assert data["exceeded"] is False

    def test_time_status_invalid_child(self, client, auth_headers):
        resp = client.get("/api/time-status?child_id=999", headers=auth_headers)
        assert resp.status_code == 404


class TestScheduleStatusEndpoint:
    def test_no_schedule_is_allowed(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get("/api/schedule-status?child_id=1", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

    def test_schedule_status_with_window(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "schedule_start", "08:00")
        store.set_child_setting(child["id"], "schedule_end", "20:00")

        resp = client.get("/api/schedule-status?child_id=1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "allowed" in data
        assert data["start"] == "8:00 AM"
        assert data["end"] == "8:00 PM"


class TestChannelsEndpoint:
    def test_list_channels(self, client, auth_headers, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Channel A", "allowed")
        store.add_channel(cid, "Channel B", "allowed")
        store.add_channel(cid, "Blocked", "blocked")

        resp = client.get(f"/api/channels?child_id={cid}", headers=auth_headers)
        assert resp.status_code == 200
        channels = resp.json()["channels"]
        assert len(channels) == 2  # Only allowed channels
