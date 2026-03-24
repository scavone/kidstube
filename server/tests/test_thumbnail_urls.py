"""Tests for thumbnail_urls field in API responses (GitHub issue #14).

Verifies that all video-returning endpoints include thumbnail_urls so the
tvOS app can cycle through frames on focus. The existing thumbnail_url field
remains the primary thumbnail; thumbnail_urls provides additional frames.
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
from api import routes as api_routes


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cfg():
    return Config(
        app_name="TestApp",
        api_key="test-secret",
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
    a = FastAPI(title="Test")
    a.state.api_key = cfg.api_key
    api_routes.setup(store, mock_invidious, cfg)
    a.include_router(api_routes.router)
    a.include_router(api_routes.public_router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth():
    return {"Authorization": "Bearer test-secret"}


# ── Helper ────────────────────────────────────────────────────────────────────

EXPECTED_URLS = [
    "https://i.ytimg.com/vi/{vid}/1.jpg",
    "https://i.ytimg.com/vi/{vid}/2.jpg",
    "https://i.ytimg.com/vi/{vid}/3.jpg",
]


def expected_thumbnail_urls(video_id: str) -> list[str]:
    return [u.format(vid=video_id) for u in EXPECTED_URLS]


# ── Route helper: _add_thumbnail_urls ────────────────────────────────────────

class TestAddThumbnailUrlsHelper:
    def test_adds_three_urls(self):
        from api.routes import _add_thumbnail_urls
        video = {"video_id": "abc12345678"}
        _add_thumbnail_urls(video)
        assert video["thumbnail_urls"] == expected_thumbnail_urls("abc12345678")

    def test_does_not_overwrite_existing(self):
        from api.routes import _add_thumbnail_urls
        existing = ["https://custom.com/thumb.jpg"]
        video = {"video_id": "abc12345678", "thumbnail_urls": existing}
        _add_thumbnail_urls(video)
        assert video["thumbnail_urls"] is existing  # unchanged

    def test_no_video_id_leaves_no_thumbnail_urls(self):
        from api.routes import _add_thumbnail_urls
        video = {"title": "No ID"}
        _add_thumbnail_urls(video)
        assert "thumbnail_urls" not in video


# ── Catalog endpoint ──────────────────────────────────────────────────────────

class TestCatalogThumbnailUrls:
    def test_catalog_videos_include_thumbnail_urls(self, client, auth, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Video 1", "Channel", thumbnail_url="https://example.com/t.jpg")
        store.request_video(child["id"], "abc12345678")
        store.update_video_status(child["id"], "abc12345678", "approved")

        resp = client.get(f"/api/catalog?child_id={child['id']}", headers=auth)
        assert resp.status_code == 200
        videos = resp.json()["videos"]
        assert len(videos) == 1
        assert videos[0]["thumbnail_urls"] == expected_thumbnail_urls("abc12345678")

    def test_catalog_preserves_existing_thumbnail_url(self, client, auth, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Video 1", "Channel", thumbnail_url="https://example.com/t.jpg")
        store.request_video(child["id"], "abc12345678")
        store.update_video_status(child["id"], "abc12345678", "approved")

        resp = client.get(f"/api/catalog?child_id={child['id']}", headers=auth)
        videos = resp.json()["videos"]
        assert videos[0]["thumbnail_url"] == "https://example.com/t.jpg"


# ── Recently Added endpoint ───────────────────────────────────────────────────

class TestRecentlyAddedThumbnailUrls:
    def test_recently_added_includes_thumbnail_urls(self, client, auth, store):
        child = store.add_child("Alex")
        store.add_video("abc12345678", "Video 1", "Channel")
        store.request_video(child["id"], "abc12345678")
        store.update_video_status(child["id"], "abc12345678", "approved")

        resp = client.get(f"/api/recently-added?child_id={child['id']}", headers=auth)
        assert resp.status_code == 200
        videos = resp.json()["videos"]
        assert len(videos) == 1
        assert videos[0]["thumbnail_urls"] == expected_thumbnail_urls("abc12345678")


# ── Video Detail endpoint ─────────────────────────────────────────────────────

class TestVideoDetailThumbnailUrls:
    def test_video_detail_from_db_includes_thumbnail_urls(self, client, auth, store, mock_invidious):
        child = store.add_child("Alex")
        # Include description so the route doesn't try to fetch from Invidious
        store.add_video("abc12345678", "Video 1", "Channel", description="A test video")

        resp = client.get(f"/api/video/abc12345678?child_id={child['id']}", headers=auth)
        assert resp.status_code == 200
        assert resp.json()["thumbnail_urls"] == expected_thumbnail_urls("abc12345678")

    def test_video_detail_from_invidious_includes_thumbnail_urls(self, client, auth, store, mock_invidious):
        child = store.add_child("Alex")
        vid = "freshvid123"  # exactly 11 chars
        mock_video = {
            "video_id": vid,
            "title": "Fresh Video",
            "channel_name": "Channel",
            "channel_id": "UC123",
            "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "thumbnail_urls": expected_thumbnail_urls(vid),
            "duration": 300,
            "published": 1700000000,
            "view_count": 1000,
            "is_family_friendly": True,
            "description": "A fresh video",
            "format_streams": [],
            "adaptive_formats": [],
            "hls_url": None,
        }
        with patch.object(mock_invidious, "get_video", new_callable=AsyncMock, return_value=mock_video):
            resp = client.get(f"/api/video/{vid}?child_id={child['id']}", headers=auth)

        assert resp.status_code == 200
        assert resp.json()["thumbnail_urls"] == expected_thumbnail_urls(vid)


# ── Search endpoint ───────────────────────────────────────────────────────────

class TestSearchThumbnailUrls:
    def test_search_video_results_include_thumbnail_urls(self, client, auth, store, mock_invidious):
        child = store.add_child("Alex")
        mock_results = [
            {
                "type": "video",
                "video_id": "abc12345678",
                "title": "Test Video",
                "channel_name": "Channel",
                "channel_id": "UC123",
                "thumbnail_url": None,
                "thumbnail_urls": expected_thumbnail_urls("abc12345678"),
                "duration": 120,
                "published": 0,
                "view_count": 0,
                "is_family_friendly": True,
                "description": "",
            }
        ]
        with patch.object(mock_invidious, "search", new_callable=AsyncMock, return_value=mock_results):
            resp = client.get(
                f"/api/search?q=test&child_id={child['id']}",
                headers=auth,
            )

        assert resp.status_code == 200
        results = resp.json()["results"]
        video_results = [r for r in results if r.get("type") == "video"]
        assert len(video_results) == 1
        assert video_results[0]["thumbnail_urls"] == expected_thumbnail_urls("abc12345678")


# ── Channels Home endpoint ────────────────────────────────────────────────────

class TestChannelsHomeThumbnailUrls:
    def test_latest_video_includes_thumbnail_urls(self, client, auth, store, mock_invidious):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Fun Channel", "allowed", channel_id="UCfun12345678901234567")
        store.add_video(
            "vid_test1234", "Test Video", "Fun Channel",
            channel_id="UCfun12345678901234567",
            published_at=1700000000,
        )
        store.request_video(child["id"], "vid_test1234")
        store.update_video_status(child["id"], "vid_test1234", "approved")

        with patch.object(mock_invidious, "get_channel_info", new_callable=AsyncMock, return_value=None):
            resp = client.get(f"/api/channels-home?child_id={child['id']}", headers=auth)

        assert resp.status_code == 200
        channels = resp.json()["channels"]
        assert len(channels) == 1
        latest = channels[0]["latest_video"]
        assert latest is not None
        assert latest["thumbnail_urls"] == expected_thumbnail_urls("vid_test1234")


# ── Channel Detail endpoint ───────────────────────────────────────────────────

class TestChannelDetailThumbnailUrls:
    def test_channel_detail_videos_include_thumbnail_urls(self, client, auth, store, mock_invidious):
        child = store.add_child("Alex")
        channel_id = "UCabcdefghijklmnopqrstuv"  # UC + 22 chars = 24 total
        store.add_channel(child["id"], "Test Channel", "allowed", channel_id=channel_id)
        store.add_video(
            "abc12345678", "Video 1", "Test Channel",
            channel_id=channel_id,
            description="test",
        )
        store.request_video(child["id"], "abc12345678")
        store.update_video_status(child["id"], "abc12345678", "approved")

        with patch.object(mock_invidious, "get_channel_info", new_callable=AsyncMock, return_value=None):
            resp = client.get(
                f"/api/channels/{channel_id}?child_id={child['id']}",
                headers=auth,
            )

        assert resp.status_code == 200
        videos = resp.json()["videos"]
        assert len(videos) == 1
        assert videos[0]["thumbnail_urls"] == expected_thumbnail_urls("abc12345678")
