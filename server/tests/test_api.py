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


    def test_catalog_filter_by_channel_id(self, client, auth_headers, store):
        """Filtering catalog by channel_id (UC...) should work like channel_name."""
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Fun Channel", "allowed", channel_id="UCfun12345678901234567")
        store.add_video("vid_fun12345", "Fun Video", "Fun Channel",
                        channel_id="UCfun12345678901234567")
        store.add_video("vid_oth12345", "Other Video", "Other Channel",
                        channel_id="UCoth12345678901234567")
        store.request_video(cid, "vid_fun12345")
        store.request_video(cid, "vid_oth12345")
        store.update_video_status(cid, "vid_oth12345", "approved")

        # Filter by channel_id
        resp = client.get(
            f"/api/catalog?child_id={cid}&channel=UCfun12345678901234567",
            headers=auth_headers,
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["videos"][0]["video_id"] == "vid_fun12345"

        # Filter by channel_name still works
        resp2 = client.get(
            f"/api/catalog?child_id={cid}&channel=Fun+Channel",
            headers=auth_headers,
        )
        assert resp2.json()["total"] == 1


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


class TestChannelsHomeEndpoint:
    """Tests for GET /api/channels-home — channel row + featured banner data."""

    def test_child_not_found(self, client, auth_headers):
        resp = client.get("/api/channels-home?child_id=999", headers=auth_headers)
        assert resp.status_code == 404

    def test_empty_channels(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get("/api/channels-home?child_id=1", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["channels"] == []

    def test_returns_channels_with_metadata(self, client, auth_headers, store, mock_invidious):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Fun Channel", "allowed", channel_id="UCfun12345678901234567")
        store.add_video("vid_test1234", "Test Video", "Fun Channel",
                        channel_id="UCfun12345678901234567",
                        thumbnail_url="http://img/thumb.jpg",
                        duration=300, published_at=1000)
        store.request_video(cid, "vid_test1234")

        mock_channel_info = {
            "channel_id": "UCfun12345678901234567",
            "name": "Fun Channel",
            "handle": "@funchannel",
            "subscriber_count": 1000,
            "description": "A fun channel",
            "thumbnail_url": "https://yt.com/avatar.jpg",
            "banner_url": "https://yt.com/banner.jpg",
        }

        with patch.object(mock_invidious, "get_channel_info",
                          new_callable=AsyncMock, return_value=mock_channel_info):
            resp = client.get(f"/api/channels-home?child_id={cid}", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["channels"]) == 1
        ch = data["channels"][0]
        assert ch["channel_name"] == "Fun Channel"
        assert ch["channel_id"] == "UCfun12345678901234567"
        assert ch["thumbnail_url"] == "https://yt.com/avatar.jpg"
        assert ch["banner_url"] == "https://yt.com/banner.jpg"
        assert ch["latest_video"]["video_id"] == "vid_test1234"
        assert ch["latest_video"]["title"] == "Test Video"

    def test_channel_without_id_has_no_metadata(self, client, auth_headers, store, mock_invidious):
        """Channels without channel_id should still appear but without Invidious metadata."""
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Local Channel", "allowed")

        resp = client.get(f"/api/channels-home?child_id={cid}", headers=auth_headers)
        assert resp.status_code == 200
        ch = resp.json()["channels"][0]
        assert ch["channel_name"] == "Local Channel"
        assert ch["thumbnail_url"] is None
        assert ch["banner_url"] is None

    def test_invidious_failure_graceful(self, client, auth_headers, store, mock_invidious):
        """If Invidious fails for a channel, the endpoint still returns data without metadata."""
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Test Channel", "allowed", channel_id="UCtst12345678901234567")

        with patch.object(mock_invidious, "get_channel_info",
                          new_callable=AsyncMock, side_effect=Exception("Connection error")):
            resp = client.get(f"/api/channels-home?child_id={cid}", headers=auth_headers)

        assert resp.status_code == 200
        ch = resp.json()["channels"][0]
        assert ch["channel_name"] == "Test Channel"
        assert ch["thumbnail_url"] is None
        assert ch["banner_url"] is None


class TestRecentlyAddedEndpoint:
    """Tests for GET /api/recently-added — recently approved videos."""

    def test_child_not_found(self, client, auth_headers):
        resp = client.get("/api/recently-added?child_id=999", headers=auth_headers)
        assert resp.status_code == 404

    def test_empty(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get("/api/recently-added?child_id=1", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["videos"] == []

    def test_returns_approved_videos(self, client, auth_headers, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "TestCh", "allowed")
        store.add_video("vid_test1234", "Test Video", "TestCh",
                        thumbnail_url="http://img.jpg", duration=120)
        store.request_video(cid, "vid_test1234")

        resp = client.get(f"/api/recently-added?child_id={cid}", headers=auth_headers)
        assert resp.status_code == 200
        videos = resp.json()["videos"]
        assert len(videos) == 1
        assert videos[0]["video_id"] == "vid_test1234"

    def test_respects_limit(self, client, auth_headers, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Ch", "allowed")
        for i in range(5):
            vid = f"vid_{i:07d}"
            store.add_video(vid, f"Video {i}", "Ch")
            store.request_video(cid, vid)

        resp = client.get(f"/api/recently-added?child_id={cid}&limit=2", headers=auth_headers)
        assert len(resp.json()["videos"]) == 2


class TestChannelDetailEndpoint:
    """Tests for GET /api/channels/{channel_id} — channel detail screen."""

    def test_child_not_found(self, client, auth_headers):
        resp = client.get(
            "/api/channels/UCtest123456789012345678?child_id=999",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_invalid_channel_id(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get(
            "/api/channels/invalid?child_id=1",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_returns_channel_with_videos(self, client, auth_headers, store, mock_invidious):
        child = store.add_child("Alex")
        cid = child["id"]
        ch_id = "UCfun1234567890123456789"
        store.add_channel(cid, "Fun Channel", "allowed",
                          channel_id=ch_id, category="fun")
        store.add_video("vid_fun12345", "Fun Video", "Fun Channel",
                        channel_id=ch_id,
                        thumbnail_url="http://img.jpg", duration=300)
        store.request_video(cid, "vid_fun12345")

        mock_info = {
            "channel_id": ch_id,
            "name": "Fun Channel",
            "handle": "@funchannel",
            "subscriber_count": 1000,
            "description": "desc",
            "thumbnail_url": "https://yt.com/avatar.jpg",
            "banner_url": "https://yt.com/banner.jpg",
        }

        with patch.object(mock_invidious, "get_channel_info",
                          new_callable=AsyncMock, return_value=mock_info):
            resp = client.get(
                f"/api/channels/{ch_id}?child_id={cid}",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["channel_name"] == "Fun Channel"
        assert data["channel_id"] == ch_id
        assert data["thumbnail_url"] == "https://yt.com/avatar.jpg"
        assert data["banner_url"] == "https://yt.com/banner.jpg"
        assert data["category"] == "fun"
        assert data["video_count"] == 1
        assert data["total"] == 1
        assert len(data["videos"]) == 1
        assert data["videos"][0]["video_id"] == "vid_fun12345"

    def test_pagination(self, client, auth_headers, store, mock_invidious):
        child = store.add_child("Alex")
        cid = child["id"]
        ch_id = "UCpag1234567890123456789"
        store.add_channel(cid, "Ch", "allowed", channel_id=ch_id)
        for i in range(5):
            vid = f"vid_p{i:06d}"
            store.add_video(vid, f"Video {i}", "Ch", channel_id=ch_id)
            store.request_video(cid, vid)

        with patch.object(mock_invidious, "get_channel_info",
                          new_callable=AsyncMock, return_value=None):
            resp = client.get(
                f"/api/channels/{ch_id}?child_id={cid}&limit=2&offset=0",
                headers=auth_headers,
            )

        data = resp.json()
        assert len(data["videos"]) == 2
        assert data["has_more"] is True
        assert data["total"] == 5
        assert data["video_count"] == 5

    def test_invidious_failure_graceful(self, client, auth_headers, store, mock_invidious):
        child = store.add_child("Alex")
        cid = child["id"]
        ch_id = "UCtst1234567890123456789"
        store.add_channel(cid, "TestCh", "allowed", channel_id=ch_id)

        with patch.object(mock_invidious, "get_channel_info",
                          new_callable=AsyncMock, side_effect=Exception("timeout")):
            resp = client.get(
                f"/api/channels/{ch_id}?child_id={cid}",
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["channel_name"] == "TestCh"
        assert data["thumbnail_url"] is None
        assert data["banner_url"] is None


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


class TestCatalogWatchStatusFilter:
    """Tests for catalog watch_status filter (#21)."""

    def _setup_catalog(self, store):
        child = store.add_child("Alex")
        store.add_video("vid_unwatche", "Unwatched Video", "Channel")
        store.add_video("vid_progress", "In Progress Video", "Channel")
        store.add_video("vid_watched1", "Watched Video", "Channel")
        for vid in ["vid_unwatche", "vid_progress", "vid_watched1"]:
            store.request_video(child["id"], vid)
            store.update_video_status(child["id"], vid, "approved")
        store.save_watch_position(child["id"], "vid_progress", 120, 600)
        store.save_watch_position(child["id"], "vid_watched1", 595, 600)
        return child

    def test_filter_all(self, client, auth_headers, store):
        self._setup_catalog(store)
        resp = client.get("/api/catalog?child_id=1&watch_status=all", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    def test_filter_unwatched(self, client, auth_headers, store):
        self._setup_catalog(store)
        resp = client.get("/api/catalog?child_id=1&watch_status=unwatched", headers=auth_headers)
        data = resp.json()
        assert data["total"] == 1
        assert data["videos"][0]["video_id"] == "vid_unwatche"

    def test_filter_in_progress(self, client, auth_headers, store):
        self._setup_catalog(store)
        resp = client.get("/api/catalog?child_id=1&watch_status=in_progress", headers=auth_headers)
        data = resp.json()
        assert data["total"] == 1
        assert data["videos"][0]["video_id"] == "vid_progress"

    def test_filter_watched(self, client, auth_headers, store):
        self._setup_catalog(store)
        resp = client.get("/api/catalog?child_id=1&watch_status=watched", headers=auth_headers)
        data = resp.json()
        assert data["total"] == 1
        assert data["videos"][0]["video_id"] == "vid_watched1"

    def test_filter_invalid_returns_400(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get("/api/catalog?child_id=1&watch_status=bogus", headers=auth_headers)
        assert resp.status_code == 400

    def test_status_counts_present(self, client, auth_headers, store):
        self._setup_catalog(store)
        resp = client.get("/api/catalog?child_id=1", headers=auth_headers)
        counts = resp.json()["status_counts"]
        assert counts["all"] == 3
        assert counts["unwatched"] == 1
        assert counts["in_progress"] == 1
        assert counts["watched"] == 1

    def test_status_counts_respect_category_filter(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("vid_edu01234", "Edu", "Ch", category="edu")
        store.add_video("vid_fun01234", "Fun", "Ch", category="fun")
        for vid in ["vid_edu01234", "vid_fun01234"]:
            store.request_video(child["id"], vid)
            store.update_video_status(child["id"], vid, "approved")
        resp = client.get("/api/catalog?child_id=1&category=edu", headers=auth_headers)
        counts = resp.json()["status_counts"]
        assert counts["all"] == 1

    def test_filter_combines_with_category(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("vid_edu01234", "Edu Unwatched", "Ch", category="edu")
        store.add_video("vid_fun01234", "Fun Unwatched", "Ch", category="fun")
        for vid in ["vid_edu01234", "vid_fun01234"]:
            store.request_video(child["id"], vid)
            store.update_video_status(child["id"], vid, "approved")
        resp = client.get(
            "/api/catalog?child_id=1&category=edu&watch_status=unwatched",
            headers=auth_headers,
        )
        assert resp.json()["total"] == 1


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
        assert resp.json()["watch_status"] == "in_progress"

    def test_save_position_auto_complete(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")

        resp = client.post("/api/watch/position", headers=auth_headers, json={
            "video_id": "abc12345678",
            "child_id": child["id"],
            "position": 590,
            "duration": 600,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "saved"
        assert data["watch_status"] == "watched"

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
        assert videos[0]["watch_status"] == "in_progress"

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


class TestWatchStatusEndpoint:
    def test_mark_watched(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")

        resp = client.post("/api/watch/status", headers=auth_headers, json={
            "video_id": "abc12345678",
            "child_id": child["id"],
            "status": "watched",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert data["watch_status"] == "watched"

    def test_mark_unwatched(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Title", "Channel")
        store.request_video(child["id"], "abc12345678")
        store.save_watch_position(child["id"], "abc12345678", 590, 600)

        resp = client.post("/api/watch/status", headers=auth_headers, json={
            "video_id": "abc12345678",
            "child_id": child["id"],
            "status": "unwatched",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert data["watch_status"] is None

        # Verify position was cleared
        pos = store.get_watch_position(child["id"], "abc12345678")
        assert pos["watch_position"] == 0

    def test_invalid_status(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.post("/api/watch/status", headers=auth_headers, json={
            "video_id": "abc12345678",
            "child_id": 1,
            "status": "foo",
        })
        assert resp.status_code == 422

    def test_invalid_video_id(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.post("/api/watch/status", headers=auth_headers, json={
            "video_id": "bad",
            "child_id": 1,
            "status": "watched",
        })
        assert resp.status_code == 400

    def test_child_not_found(self, client, auth_headers):
        resp = client.post("/api/watch/status", headers=auth_headers, json={
            "video_id": "abc12345678",
            "child_id": 999,
            "status": "watched",
        })
        assert resp.status_code == 404

    def test_no_access_record(self, client, auth_headers, store):
        child = store.add_child("Alex")
        resp = client.post("/api/watch/status", headers=auth_headers, json={
            "video_id": "abc12345678",
            "child_id": child["id"],
            "status": "watched",
        })
        assert resp.status_code == 404


class TestChannelRequestEndpoint:
    def test_request_channel_pending(self, client, auth_headers, store):
        store.add_child("Alex")
        with patch.object(
            InvidiousClient, "get_channel_info",
            new_callable=AsyncMock,
            return_value={"channel_id": "UCabcdef12345678901234AB", "name": "Cool Channel", "subscriber_count": 1000},
        ):
            resp = client.post("/api/request-channel", headers=auth_headers, json={
                "child_id": 1,
                "channel_id": "UCabcdef12345678901234AB",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["channel_name"] == "Cool Channel"
        assert data["channel_id"] == "UCabcdef12345678901234AB"

    def test_request_channel_already_allowed(self, client, auth_headers, store):
        store.add_child("Alex")
        store.add_channel(1, "Cool Channel", "allowed", channel_id="UCabcdef12345678901234AB")
        with patch.object(
            InvidiousClient, "get_channel_info",
            new_callable=AsyncMock,
            return_value={"channel_id": "UCabcdef12345678901234AB", "name": "Cool Channel", "subscriber_count": 1000},
        ):
            resp = client.post("/api/request-channel", headers=auth_headers, json={
                "child_id": 1,
                "channel_id": "UCabcdef12345678901234AB",
            })
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_request_channel_child_not_found(self, client, auth_headers):
        with patch.object(
            InvidiousClient, "get_channel_info",
            new_callable=AsyncMock,
            return_value={"channel_id": "UCabcdef12345678901234AB", "name": "Cool Channel"},
        ):
            resp = client.post("/api/request-channel", headers=auth_headers, json={
                "child_id": 999,
                "channel_id": "UCabcdef12345678901234AB",
            })
        assert resp.status_code == 404

    def test_request_channel_invalid_id(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.post("/api/request-channel", headers=auth_headers, json={
            "child_id": 1,
            "channel_id": "invalid",
        })
        assert resp.status_code == 422  # Pydantic validation

    def test_channel_request_status_polling(self, client, auth_headers, store):
        store.add_child("Alex")
        store.request_channel(1, "UCabcdef12345678901234AB", "Cool Channel")
        resp = client.get(
            "/api/channel-request-status/UCabcdef12345678901234AB",
            headers=auth_headers,
            params={"child_id": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_channel_request_status_not_found(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get(
            "/api/channel-request-status/UCabcdef12345678901234AB",
            headers=auth_headers,
            params={"child_id": 1},
        )
        assert resp.status_code == 404

    def test_search_annotates_channel_status(self, client, auth_headers, store):
        store.add_child("Alex")
        store.add_channel(1, "Allowed Ch", "allowed")
        with patch.object(
            InvidiousClient, "search",
            new_callable=AsyncMock,
            return_value=[
                {"type": "channel", "channel_id": "UC_allowed", "name": "Allowed Ch"},
                {"type": "channel", "channel_id": "UC_unknown", "name": "New Ch"},
            ],
        ):
            resp = client.get(
                "/api/search",
                headers=auth_headers,
                params={"q": "test", "child_id": 1},
            )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        assert results[0]["channel_status"] == "allowed"
        assert results[1].get("channel_status") is None


class TestBonusTime:
    def test_remaining_includes_bonus(self, client, auth_headers, store):
        """_get_remaining_seconds adds bonus minutes to the limit."""
        child = store.add_child("Alex")
        cid = child["id"]
        store.set_child_setting(cid, "daily_limit_minutes", "30")
        # Use up 29 minutes of watch time
        from utils import get_today_str, get_day_utc_bounds
        tz = "America/New_York"
        today = get_today_str(tz)
        store.record_watch_seconds("vid12345678", cid, 29 * 60)
        # Without bonus, only ~1 min remaining
        resp = client.get(f"/api/time-status?child_id={cid}", headers=auth_headers)
        data = resp.json()
        assert data["remaining_min"] <= 1.0

        # Add 15 min bonus for today
        store.set_child_setting(cid, "bonus_minutes_date", today)
        store.set_child_setting(cid, "bonus_minutes", "15")

        resp = client.get(f"/api/time-status?child_id={cid}", headers=auth_headers)
        data = resp.json()
        assert data["remaining_min"] > 14.0  # ~16 min remaining now
        assert data["exceeded"] is False

    def test_bonus_only_applies_for_today(self, client, auth_headers, store):
        """Bonus from a different date does not apply."""
        child = store.add_child("Alex")
        cid = child["id"]
        store.set_child_setting(cid, "daily_limit_minutes", "10")
        # Set bonus for yesterday
        store.set_child_setting(cid, "bonus_minutes_date", "2020-01-01")
        store.set_child_setting(cid, "bonus_minutes", "30")

        resp = client.get(f"/api/time-status?child_id={cid}", headers=auth_headers)
        data = resp.json()
        assert data["limit_min"] == 10  # no bonus added
        assert data["remaining_min"] == 10.0

    def test_heartbeat_includes_bonus(self, client, auth_headers, store):
        """Heartbeat remaining calculation includes bonus time."""
        child = store.add_child("Alex")
        cid = child["id"]
        store.set_child_setting(cid, "daily_limit_minutes", "1")
        vid = "dQw4w9WgXcQ"
        store.add_video(vid, "Test Video", "Channel")
        store.request_video(cid, vid)
        store.update_video_status(cid, vid, "approved")

        # Send heartbeat — should have ~60 seconds remaining
        resp = client.post(
            "/api/watch-heartbeat", headers=auth_headers,
            json={"video_id": vid, "child_id": cid, "seconds": 0},
        )
        assert resp.status_code == 200
        remaining_before = resp.json()["remaining"]

        # Add bonus
        from utils import get_today_str
        today = get_today_str("America/New_York")
        store.set_child_setting(cid, "bonus_minutes_date", today)
        store.set_child_setting(cid, "bonus_minutes", "10")

        resp = client.post(
            "/api/watch-heartbeat", headers=auth_headers,
            json={"video_id": vid, "child_id": cid, "seconds": 0},
        )
        assert resp.status_code == 200
        remaining_after = resp.json()["remaining"]
        assert remaining_after > remaining_before


class TestTimeRequestEndpoint:
    def test_create_time_request(self, client, auth_headers, store):
        """POST /api/time-request creates a pending request."""
        child = store.add_child("Alex")
        cid = child["id"]

        resp = client.post(
            "/api/time-request", headers=auth_headers,
            json={"child_id": cid},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["bonus_minutes"] == 0

    def test_time_request_idempotent(self, client, auth_headers, store):
        """Duplicate POST returns pending without creating a new request."""
        child = store.add_child("Alex")
        cid = child["id"]

        client.post("/api/time-request", headers=auth_headers, json={"child_id": cid})
        resp = client.post("/api/time-request", headers=auth_headers, json={"child_id": cid})
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_time_request_status_none(self, client, auth_headers, store):
        """GET /api/time-request/status returns none when no request exists."""
        child = store.add_child("Alex")
        cid = child["id"]

        resp = client.get(f"/api/time-request/status?child_id={cid}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "none"

    def test_time_request_status_pending(self, client, auth_headers, store):
        """GET returns pending after POST."""
        child = store.add_child("Alex")
        cid = child["id"]

        client.post("/api/time-request", headers=auth_headers, json={"child_id": cid})
        resp = client.get(f"/api/time-request/status?child_id={cid}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_time_request_granted_status(self, client, auth_headers, store):
        """GET returns granted + bonus after parent grants time."""
        child = store.add_child("Alex")
        cid = child["id"]
        from utils import get_today_str
        today = get_today_str("America/New_York")

        client.post("/api/time-request", headers=auth_headers, json={"child_id": cid})
        # Simulate parent granting time
        store.set_child_setting(cid, "time_request_status", "granted")
        store.set_child_setting(cid, "bonus_minutes_date", today)
        store.set_child_setting(cid, "bonus_minutes", "15")

        resp = client.get(f"/api/time-request/status?child_id={cid}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "granted"
        assert data["bonus_minutes"] == 15

    def test_time_request_returns_granted_if_already_granted(self, client, auth_headers, store):
        """POST returns granted + bonus if already granted today."""
        child = store.add_child("Alex")
        cid = child["id"]
        from utils import get_today_str
        today = get_today_str("America/New_York")

        store.set_child_setting(cid, "time_request_date", today)
        store.set_child_setting(cid, "time_request_status", "granted")
        store.set_child_setting(cid, "bonus_minutes_date", today)
        store.set_child_setting(cid, "bonus_minutes", "30")

        resp = client.post("/api/time-request", headers=auth_headers, json={"child_id": cid})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "granted"
        assert data["bonus_minutes"] == 30

    def test_time_request_invalid_child(self, client, auth_headers):
        """POST returns 404 for nonexistent child."""
        resp = client.post(
            "/api/time-request", headers=auth_headers,
            json={"child_id": 999},
        )
        assert resp.status_code == 404

    def test_heartbeat_finish_video_sentinel(self, client, auth_headers, store):
        """Heartbeat returns -3 when time is up but parent granted finish-video."""
        child = store.add_child("Alex")
        cid = child["id"]
        vid = "dQw4w9WgXcQ"
        store.set_child_setting(cid, "daily_limit_minutes", "1")
        store.add_video(vid, "Test Video", "Channel")
        store.request_video(cid, vid)
        store.update_video_status(cid, vid, "approved")
        # Use up all time
        store.record_watch_seconds(vid, cid, 120)

        from utils import get_today_str
        today = get_today_str("America/New_York")
        store.set_child_setting(cid, "finish_video_date", today)
        store.set_child_setting(cid, "finish_video_id", vid)

        resp = client.post(
            "/api/watch-heartbeat", headers=auth_headers,
            json={"video_id": vid, "child_id": cid, "seconds": 0},
        )
        assert resp.status_code == 200
        assert resp.json()["remaining"] == -3


# ── Pairing Endpoints ──────────────────────────────────────────────

class TestPairingEndpoints:
    """Tests for the device pairing workflow."""

    def test_pair_request_returns_token_and_pin(self, client):
        """POST /api/pair/request returns token, pin, expires_at, expires_in."""
        resp = client.post("/api/pair/request")
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "pin" in data
        assert len(data["pin"]) == 6
        assert data["pin"].isdigit()
        assert "expires_at" in data
        assert "expires_in" in data
        assert data["expires_in"] > 0

    def test_pair_request_no_auth_needed(self, client):
        """Pairing request does not require auth."""
        resp = client.post("/api/pair/request")
        assert resp.status_code == 200

    def test_pair_request_with_device_name(self, client):
        """Can provide optional device_name."""
        resp = client.post("/api/pair/request", json={"device_name": "Living Room TV"})
        assert resp.status_code == 200

    def test_pair_status_pending(self, client):
        """New pairing starts as pending."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]
        resp = client.get(f"/api/pair/status/{token}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_pair_status_no_auth_needed(self, client):
        """Status polling does not require auth."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]
        resp = client.get(f"/api/pair/status/{token}")
        assert resp.status_code == 200

    def test_pair_status_unknown_token(self, client):
        """Unknown token returns 404."""
        resp = client.get("/api/pair/status/nonexistent-token")
        assert resp.status_code == 404

    def test_pair_confirm_requires_auth(self, client):
        """Confirm requires admin auth."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]
        resp = client.post(f"/api/pair/confirm/{token}")
        assert resp.status_code == 401

    def test_pair_confirm_success(self, client, auth_headers):
        """Admin can confirm pairing and get device api_key."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]
        resp = client.post(f"/api/pair/confirm/{token}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"
        assert "api_key" in data
        assert "device_id" in data

    def test_pair_confirm_by_pin(self, client, auth_headers):
        """Admin can confirm by entering the PIN."""
        create_resp = client.post("/api/pair/request")
        pin = create_resp.json()["pin"]
        resp = client.post("/api/pair/confirm-by-pin",
                           json={"pin": pin}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

    def test_pair_status_after_confirm(self, client, auth_headers):
        """After confirm, status shows confirmed with api_key."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]
        client.post(f"/api/pair/confirm/{token}", headers=auth_headers)
        resp = client.get(f"/api/pair/status/{token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"
        assert data["api_key"] is not None
        assert len(data["api_key"]) >= 32

    def test_device_key_works_for_auth(self, client, auth_headers):
        """Issued device key can authenticate to protected endpoints."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]
        confirm_resp = client.post(f"/api/pair/confirm/{token}", headers=auth_headers)
        new_key = confirm_resp.json()["api_key"]
        resp = client.get("/api/profiles",
                          headers={"Authorization": f"Bearer {new_key}"})
        assert resp.status_code == 200

    def test_list_devices(self, client, auth_headers):
        """GET /api/devices lists paired devices."""
        create_resp = client.post("/api/pair/request",
                                  json={"device_name": "Test TV"})
        token = create_resp.json()["token"]
        client.post(f"/api/pair/confirm/{token}", headers=auth_headers)
        resp = client.get("/api/devices", headers=auth_headers)
        assert resp.status_code == 200
        devices = resp.json()["devices"]
        assert len(devices) >= 1
        assert any(d["device_name"] == "Test TV" for d in devices)

    def test_list_devices_requires_auth(self, client):
        resp = client.get("/api/devices")
        assert resp.status_code == 401

    def test_revoke_device(self, client, auth_headers):
        """DELETE /api/devices/{id} revokes a device."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]
        confirm_resp = client.post(f"/api/pair/confirm/{token}", headers=auth_headers)
        device_key = confirm_resp.json()["api_key"]
        devices = client.get("/api/devices", headers=auth_headers).json()["devices"]
        device_id = devices[0]["id"]
        resp = client.delete(f"/api/devices/{device_id}", headers=auth_headers)
        assert resp.status_code == 200
        # Verify revoked key no longer works
        resp = client.get("/api/profiles",
                          headers={"Authorization": f"Bearer {device_key}"})
        assert resp.status_code == 401

    def test_revoke_nonexistent_device(self, client, auth_headers):
        resp = client.delete("/api/devices/999", headers=auth_headers)
        assert resp.status_code == 404

    def test_double_confirm_returns_409(self, client, auth_headers):
        """Confirming an already-confirmed pairing returns 409."""
        create_resp = client.post("/api/pair/request")
        token = create_resp.json()["token"]
        client.post(f"/api/pair/confirm/{token}", headers=auth_headers)
        resp = client.post(f"/api/pair/confirm/{token}", headers=auth_headers)
        assert resp.status_code == 409
