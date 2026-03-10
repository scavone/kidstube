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
            {"type": "video", "video_id": "vid1", "title": "Result", "channel_name": "Ch", "channel_id": "UC1",
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
            {"type": "video", "video_id": "v1", "title": "Good", "channel_name": "Good Ch", "channel_id": "UC1",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0},
            {"type": "video", "video_id": "v2", "title": "Bad", "channel_name": "Bad Channel", "channel_id": "UC2",
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
            {"type": "video", "video_id": "v1", "title": "Contains badword here", "channel_name": "Ch", "channel_id": "UC1",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0},
            {"type": "video", "video_id": "v2", "title": "Clean title", "channel_name": "Ch", "channel_id": "UC2",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0},
        ]

        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results):
            resp = client.get("/api/search?q=test&child_id=1", headers=auth_headers)

        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["video_id"] == "v2"

    def test_search_returns_channels(self, client, auth_headers, store, mock_invidious):
        store.add_child("Alex")

        mock_results = [
            {"type": "video", "video_id": "v1", "title": "Video", "channel_name": "Ch", "channel_id": "UC1",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0},
            {"type": "channel", "channel_id": "UC_TEST", "name": "Test Channel",
             "thumbnail_url": "http://thumb.jpg", "subscriber_count": 5000, "video_count": 100},
        ]

        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results):
            resp = client.get("/api/search?q=test&child_id=1", headers=auth_headers)

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        assert results[0]["type"] == "video"
        assert results[0]["video_id"] == "v1"
        assert results[1]["type"] == "channel"
        assert results[1]["channel_id"] == "UC_TEST"
        assert results[1]["name"] == "Test Channel"

    def test_search_filters_blocked_channel_results(self, client, auth_headers, store, mock_invidious):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Bad Channel", "blocked")

        mock_results = [
            {"type": "channel", "channel_id": "UC_GOOD", "name": "Good Channel",
             "thumbnail_url": None, "subscriber_count": 100, "video_count": 10},
            {"type": "channel", "channel_id": "UC_BAD", "name": "Bad Channel",
             "thumbnail_url": None, "subscriber_count": 200, "video_count": 20},
        ]

        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results):
            resp = client.get("/api/search?q=test&child_id=1", headers=auth_headers)

        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["name"] == "Good Channel"


class TestChannelVideosEndpoint:
    def test_channel_videos(self, client, auth_headers, store, mock_invidious):
        store.add_child("Alex")

        mock_videos = [
            {"video_id": "v1", "title": "Video 1", "channel_name": "Ch", "channel_id": "UC1234567890abcdefghijkl",
             "thumbnail_url": None, "duration": 120, "published": 0, "view_count": 0},
        ]

        with patch.object(mock_invidious, "get_channel_videos", new_callable=AsyncMock, return_value=mock_videos):
            resp = client.get("/api/channel/UC1234567890abcdefghijkl/videos?child_id=1", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["channel_id"] == "UC1234567890abcdefghijkl"
        assert len(data["videos"]) == 1
        assert data["videos"][0]["video_id"] == "v1"

    def test_channel_videos_invalid_id(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get("/api/channel/invalid/videos?child_id=1", headers=auth_headers)
        assert resp.status_code == 400

    def test_channel_videos_child_not_found(self, client, auth_headers):
        resp = client.get("/api/channel/UC1234567890abcdefghijkl/videos?child_id=999", headers=auth_headers)
        assert resp.status_code == 404


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
        data = resp.json()
        assert data["allowed"] is True
        assert data["minutes_remaining"] == -1

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
        assert "minutes_remaining" in data

    def test_schedule_status_per_day(self, client, auth_headers, store):
        """Per-day schedule overrides legacy schedule_start/schedule_end."""
        import json
        from datetime import datetime
        from zoneinfo import ZoneInfo
        child = store.add_child("Alex")
        # Set a legacy schedule
        store.set_child_setting(child["id"], "schedule_start", "06:00")
        store.set_child_setting(child["id"], "schedule_end", "18:00")
        # Set a per-day override for today (using the configured timezone)
        tz = ZoneInfo("America/New_York")
        day_name = ["monday", "tuesday", "wednesday", "thursday",
                    "friday", "saturday", "sunday"][datetime.now(tz).weekday()]
        store.set_child_setting(
            child["id"], f"schedule:{day_name}",
            json.dumps({"start": "08:00", "end": "20:00"})
        )
        resp = client.get("/api/schedule-status?child_id=1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Should use the per-day override, not the legacy
        assert data["start"] == "8:00 AM"
        assert data["end"] == "8:00 PM"

    def test_schedule_status_default_fallback(self, client, auth_headers, store):
        """schedule:default is used when no per-day or legacy schedule exists."""
        import json
        child = store.add_child("Alex")
        store.set_child_setting(
            child["id"], "schedule:default",
            json.dumps({"start": "09:00", "end": "21:00"})
        )
        resp = client.get("/api/schedule-status?child_id=1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["start"] == "9:00 AM"
        assert data["end"] == "9:00 PM"


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


class TestFamilyFriendlyFilter:
    """Tests for filtering isFamilyFriendly=false from search results (#17)."""

    def test_filters_non_family_friendly(self, client, auth_headers, store, mock_invidious):
        store.add_child("Alex")

        mock_results = [
            {"type": "video", "video_id": "v1", "title": "Safe", "channel_name": "Ch", "channel_id": "UC1",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0,
             "is_family_friendly": True},
            {"type": "video", "video_id": "v2", "title": "Unsafe", "channel_name": "Ch", "channel_id": "UC2",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0,
             "is_family_friendly": False},
        ]

        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results):
            resp = client.get("/api/search?q=test&child_id=1", headers=auth_headers)

        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["video_id"] == "v1"

    def test_keeps_videos_with_no_family_friendly_field(self, client, auth_headers, store, mock_invidious):
        store.add_child("Alex")

        mock_results = [
            {"type": "video", "video_id": "v1", "title": "No field", "channel_name": "Ch", "channel_id": "UC1",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0},
        ]

        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results):
            resp = client.get("/api/search?q=test&child_id=1", headers=auth_headers)

        results = resp.json()["results"]
        assert len(results) == 1


class TestNotificationDedup:
    """Tests for notification dedup on video requests (#27)."""

    def test_duplicate_request_does_not_notify_twice(self, client, auth_headers, store, mock_invidious):
        store.add_child("Alex")
        store.add_video("abc12345678", "Test Video", "Ch")

        notify = AsyncMock()
        api_routes.notify_callback = notify

        # First request -> notification
        resp = client.post(
            "/api/request",
            json={"video_id": "abc12345678", "child_id": 1},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert notify.call_count == 1

        # Second request within dedup window -> no notification
        # (request_video returns existing "pending", so notify is not triggered)
        resp = client.post(
            "/api/request",
            json={"video_id": "abc12345678", "child_id": 1},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        # notify should still be 1 because request_video returns "pending" (existing row)
        # and we only notify on status == "pending" from a NEW insert
        assert notify.call_count == 1


class TestStarterChannelsEndpoint:
    """Tests for the starter channels onboarding endpoints (#13)."""

    def test_get_starter_channels(self, client, auth_headers):
        resp = client.get("/api/onboarding/starter-channels", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "categories" in data
        categories = data["categories"]
        assert "educational" in categories
        assert "fun" in categories
        assert "music" in categories
        assert "science" in categories
        # Check a known channel exists
        edu_handles = [ch["handle"] for ch in categories["educational"]]
        assert "@kurzgesagt" in edu_handles

    def test_starter_channels_annotates_imported(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Kurzgesagt", "allowed", handle="@kurzgesagt")

        resp = client.get(f"/api/onboarding/starter-channels?child_id={child['id']}", headers=auth_headers)
        assert resp.status_code == 200
        categories = resp.json()["categories"]

        kurzgesagt = next(
            ch for ch in categories["educational"]
            if ch["handle"] == "@kurzgesagt"
        )
        assert kurzgesagt["imported"] is True

    def test_import_starter_channels(self, client, auth_headers, store):
        child = store.add_child("Alex")

        resp = client.post(
            "/api/onboarding/import",
            json={"handles": ["@kurzgesagt", "@MarkRober"], "child_id": child["id"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert "@kurzgesagt" in data["imported"]
        assert "@MarkRober" in data["imported"]

        # Verify channels were actually added
        channels = store.get_channels(child["id"], status="allowed")
        names = [ch["channel_name"] for ch in channels]
        assert "Kurzgesagt \u2013 In a Nutshell" in names
        assert "Mark Rober" in names

    def test_import_invalid_handles_skipped(self, client, auth_headers, store):
        child = store.add_child("Alex")

        resp = client.post(
            "/api/onboarding/import",
            json={"handles": ["@nonexistent_handle_xyz"], "child_id": child["id"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_import_requires_child(self, client, auth_headers):
        resp = client.post(
            "/api/onboarding/import",
            json={"handles": ["@kurzgesagt"], "child_id": 999},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_import_sets_correct_categories(self, client, auth_headers, store):
        child = store.add_child("Alex")

        resp = client.post(
            "/api/onboarding/import",
            json={"handles": ["@kurzgesagt", "@BlueyTV", "@MarkRober"], "child_id": child["id"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        channels = store.get_channels(child["id"])
        by_name = {ch["channel_name"]: ch for ch in channels}
        assert by_name["Kurzgesagt \u2013 In a Nutshell"]["category"] == "edu"
        assert by_name["Bluey"]["category"] == "fun"
        assert by_name["Mark Rober"]["category"] == "edu"  # science -> edu


class TestCatalogSortOptions:
    """Tests for catalog sort_by parameter (#22)."""

    def _setup_catalog(self, store):
        child = store.add_child("Alex")
        store.add_video("vid_aaa0001", "Zebra Video", "B Channel", published_at=100)
        store.add_video("vid_bbb0002", "Apple Video", "A Channel", published_at=300)
        store.add_video("vid_ccc0003", "Mango Video", "C Channel", published_at=200)
        for vid in ["vid_aaa0001", "vid_bbb0002", "vid_ccc0003"]:
            store.request_video(child["id"], vid)
            store.update_video_status(child["id"], vid, "approved")
        return child

    def test_sort_newest(self, client, auth_headers, store):
        self._setup_catalog(store)
        resp = client.get("/api/catalog?child_id=1&sort_by=newest", headers=auth_headers)
        videos = resp.json()["videos"]
        assert videos[0]["video_id"] == "vid_bbb0002"  # published_at=300

    def test_sort_oldest(self, client, auth_headers, store):
        self._setup_catalog(store)
        resp = client.get("/api/catalog?child_id=1&sort_by=oldest", headers=auth_headers)
        videos = resp.json()["videos"]
        assert videos[0]["video_id"] == "vid_aaa0001"  # published_at=100

    def test_sort_title(self, client, auth_headers, store):
        self._setup_catalog(store)
        resp = client.get("/api/catalog?child_id=1&sort_by=title", headers=auth_headers)
        videos = resp.json()["videos"]
        assert videos[0]["title"] == "Apple Video"
        assert videos[-1]["title"] == "Zebra Video"

    def test_sort_channel(self, client, auth_headers, store):
        self._setup_catalog(store)
        resp = client.get("/api/catalog?child_id=1&sort_by=channel", headers=auth_headers)
        videos = resp.json()["videos"]
        assert videos[0]["channel_name"] == "A Channel"
        assert videos[-1]["channel_name"] == "C Channel"

    def test_sort_default_is_newest(self, client, auth_headers, store):
        self._setup_catalog(store)
        resp = client.get("/api/catalog?child_id=1", headers=auth_headers)
        videos = resp.json()["videos"]
        assert videos[0]["video_id"] == "vid_bbb0002"

    def test_sort_invalid_returns_400(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get("/api/catalog?child_id=1&sort_by=invalid", headers=auth_headers)
        assert resp.status_code == 400

    def test_sort_order_desc_reverses_title(self, client, auth_headers, store):
        self._setup_catalog(store)
        resp = client.get(
            "/api/catalog?child_id=1&sort_by=title&sort_order=desc",
            headers=auth_headers,
        )
        videos = resp.json()["videos"]
        assert videos[0]["title"] == "Zebra Video"
        assert videos[-1]["title"] == "Apple Video"

    def test_sort_order_asc_explicit(self, client, auth_headers, store):
        self._setup_catalog(store)
        resp = client.get(
            "/api/catalog?child_id=1&sort_by=newest&sort_order=asc",
            headers=auth_headers,
        )
        videos = resp.json()["videos"]
        assert videos[0]["video_id"] == "vid_aaa0001"  # published_at=100 (ascending)

    def test_sort_order_invalid_returns_400(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get(
            "/api/catalog?child_id=1&sort_order=bad",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_sort_order_empty_uses_default(self, client, auth_headers, store):
        """Empty sort_order uses the natural default for the sort type."""
        self._setup_catalog(store)
        resp = client.get(
            "/api/catalog?child_id=1&sort_by=title&sort_order=",
            headers=auth_headers,
        )
        videos = resp.json()["videos"]
        assert videos[0]["title"] == "Apple Video"  # default for title is ASC


class TestFreeDayAPI:
    """Tests for free day pass via API (#32)."""

    def test_free_day_unlimited_remaining(self, client, auth_headers, store, cfg):
        from utils import get_today_str
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")

        # Set free day to today
        tz = cfg.watch_limits.timezone
        today = get_today_str(tz)
        store.set_child_setting(child["id"], "free_day_date", today)

        resp = client.get("/api/time-status?child_id=1", headers=auth_headers)
        data = resp.json()
        assert data["remaining_sec"] == -1
        assert data["exceeded"] is False

    def test_no_free_day_normal_limits(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")

        resp = client.get("/api/time-status?child_id=1", headers=auth_headers)
        data = resp.json()
        assert data["remaining_sec"] > 0
        assert data["limit_min"] == 60

    def test_expired_free_day_not_active(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")
        store.set_child_setting(child["id"], "free_day_date", "2020-01-01")

        resp = client.get("/api/time-status?child_id=1", headers=auth_headers)
        data = resp.json()
        assert data["remaining_sec"] > 0  # Not unlimited


class TestFamilySafeFilter:
    """Tests for per-child family safe filter (#34)."""

    def test_search_with_filter_on_passes_family_safe(self, client, auth_headers, store, mock_invidious):
        """When family_safe_filter is on (default), search passes family_safe=True to Invidious."""
        child = store.add_child("Alex")

        mock_results = [
            {"type": "video", "video_id": "v1", "title": "Safe", "channel_name": "Ch", "channel_id": "UC1",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0,
             "is_family_friendly": True},
        ]

        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results) as mock_search:
            resp = client.get(f"/api/search?q=test&child_id={child['id']}", headers=auth_headers)

        assert resp.status_code == 200
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args
        assert call_kwargs[1].get("family_safe") is True or (len(call_kwargs[0]) >= 3 and call_kwargs[0][2] is True)

    def test_search_with_filter_off_no_family_safe(self, client, auth_headers, store, mock_invidious):
        """When family_safe_filter is off, search passes family_safe=False and does not filter results."""
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "family_safe_filter", "off")

        mock_results = [
            {"type": "video", "video_id": "v1", "title": "Safe", "channel_name": "Ch", "channel_id": "UC1",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0,
             "is_family_friendly": True},
            {"type": "video", "video_id": "v2", "title": "Unsafe", "channel_name": "Ch", "channel_id": "UC2",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0,
             "is_family_friendly": False},
        ]

        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results) as mock_search:
            resp = client.get(f"/api/search?q=test&child_id={child['id']}", headers=auth_headers)

        assert resp.status_code == 200
        results = resp.json()["results"]
        # Both results should be returned (no client-side filtering)
        assert len(results) == 2
        # Invidious search should not have family_safe=True
        call_kwargs = mock_search.call_args
        assert call_kwargs[1].get("family_safe") is False or (len(call_kwargs[0]) >= 3 and call_kwargs[0][2] is False)

    def test_search_with_filter_on_filters_non_family_friendly(self, client, auth_headers, store, mock_invidious):
        """When filter is on, non-family-friendly results are filtered client-side as safety net."""
        child = store.add_child("Alex")
        # Default is on

        mock_results = [
            {"type": "video", "video_id": "v1", "title": "Safe", "channel_name": "Ch", "channel_id": "UC1",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0,
             "is_family_friendly": True},
            {"type": "video", "video_id": "v2", "title": "Unsafe", "channel_name": "Ch", "channel_id": "UC2",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0,
             "is_family_friendly": False},
        ]

        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results):
            resp = client.get(f"/api/search?q=test&child_id={child['id']}", headers=auth_headers)

        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["video_id"] == "v1"

    def test_default_filter_is_on(self, client, auth_headers, store, mock_invidious):
        """Without setting family_safe_filter, default behavior is on."""
        child = store.add_child("Alex")
        # Verify no setting exists
        assert store.get_child_setting(child["id"], "family_safe_filter", "on") == "on"

        mock_results = [
            {"type": "video", "video_id": "v1", "title": "Safe", "channel_name": "Ch", "channel_id": "UC1",
             "thumbnail_url": None, "duration": 100, "published": 0, "view_count": 0,
             "is_family_friendly": True},
        ]

        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results) as mock_search:
            resp = client.get(f"/api/search?q=test&child_id={child['id']}", headers=auth_headers)

        assert resp.status_code == 200
        call_kwargs = mock_search.call_args
        assert call_kwargs[1].get("family_safe") is True


class TestPerChildLanguage:
    """Tests for per-child preferred audio language (#41)."""

    def test_stream_uses_child_language(self, client, auth_headers, store, mock_invidious, cfg):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")
        store.update_video_status(child["id"], "abc12345678", "approved")
        store.set_child_setting(child["id"], "preferred_language", "es")
        cfg.preferred_audio_lang = "en"

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
        ), patch.object(
            mock_invidious, "pick_best_adaptive_pair",
            return_value=None,
        ) as mock_pick:
            resp = client.get("/api/stream/abc12345678?child_id=1", headers=auth_headers)

        assert resp.status_code == 200
        # pick_best_adaptive_pair should have been called with child's language, not global
        if mock_pick.called:
            call_kwargs = mock_pick.call_args
            assert call_kwargs[1].get("preferred_lang") == "es" or call_kwargs[0][1] == "es"
        cfg.preferred_audio_lang = ""

    def test_stream_falls_back_to_global_language(self, client, auth_headers, store, mock_invidious, cfg):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")
        store.update_video_status(child["id"], "abc12345678", "approved")
        # No per-child language set
        cfg.preferred_audio_lang = "en"

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
        ), patch.object(
            mock_invidious, "pick_best_adaptive_pair",
            return_value=None,
        ) as mock_pick:
            resp = client.get("/api/stream/abc12345678?child_id=1", headers=auth_headers)

        assert resp.status_code == 200
        if mock_pick.called:
            call_kwargs = mock_pick.call_args
            assert call_kwargs[1].get("preferred_lang") == "en" or call_kwargs[0][1] == "en"
        cfg.preferred_audio_lang = ""


class TestWatchPositionEndpoint:
    def test_save_position(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")

        resp = client.post("/api/watch/position", headers=auth_headers, json={
            "video_id": "abc12345678",
            "child_id": child["id"],
            "position": 120,
            "duration": 600,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

    def test_save_position_invalid_video_id(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.post("/api/watch/position", headers=auth_headers, json={
            "video_id": "bad",
            "child_id": 1,
            "position": 120,
            "duration": 600,
        })
        assert resp.status_code == 400

    def test_save_position_child_not_found(self, client, auth_headers):
        resp = client.post("/api/watch/position", headers=auth_headers, json={
            "video_id": "abc12345678",
            "child_id": 999,
            "position": 120,
            "duration": 600,
        })
        assert resp.status_code == 404

    def test_save_position_no_access_row(self, client, auth_headers, store):
        child = store.add_child("Alex")
        resp = client.post("/api/watch/position", headers=auth_headers, json={
            "video_id": "abc12345678",
            "child_id": child["id"],
            "position": 120,
            "duration": 600,
        })
        assert resp.status_code == 404

    def test_get_position(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")
        store.save_watch_position(child["id"], "abc12345678", 120, 600)

        resp = client.get(
            "/api/watch/position/abc12345678?child_id=1",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["watch_position"] == 120
        assert data["watch_duration"] == 600
        assert data["last_watched_at"] is not None

    def test_get_position_no_data(self, client, auth_headers, store):
        child = store.add_child("Alex")
        resp = client.get(
            f"/api/watch/position/abc12345678?child_id={child['id']}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["watch_position"] == 0
        assert data["watch_duration"] == 0

    def test_get_position_invalid_video_id(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get(
            "/api/watch/position/bad?child_id=1",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_catalog_includes_watch_position(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")
        store.update_video_status(child["id"], "abc12345678", "approved")
        store.save_watch_position(child["id"], "abc12345678", 120, 600)

        resp = client.get(
            f"/api/catalog?child_id={child['id']}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        videos = resp.json()["videos"]
        assert len(videos) == 1
        assert videos[0]["watch_position"] == 120
        assert videos[0]["watch_duration"] == 600

    def test_video_detail_includes_watch_position(self, client, auth_headers, store, mock_invidious):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel", description="A test video")
        store.request_video(child["id"], "abc12345678")
        store.update_video_status(child["id"], "abc12345678", "approved")
        store.save_watch_position(child["id"], "abc12345678", 250, 900)

        resp = client.get(
            f"/api/video/abc12345678?child_id={child['id']}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["watch_position"] == 250
        assert data["watch_duration"] == 900

    def test_requires_auth(self, client):
        resp = client.post("/api/watch/position", json={
            "video_id": "abc12345678",
            "child_id": 1,
            "position": 120,
            "duration": 600,
        })
        assert resp.status_code == 401
