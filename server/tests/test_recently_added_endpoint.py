"""Test plan for Issue #7: GET /api/recently-added endpoint.

Returns recently approved videos for a child, ordered by approval date descending.
Powers the 'Recently Added' row on the tvOS home screen.

Expected endpoint: GET /api/recently-added?child_id=N&limit=M
Expected response: { "videos": [ { ...video dict with watch metadata... } ] }
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


# ── Tests ─────────────────────────────────────────────────────────

class TestRecentlyAddedAuth:
    """Auth is required for the recently-added endpoint."""

    def test_missing_auth_returns_401(self, client):
        resp = client.get("/api/recently-added", params={"child_id": 1})
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client):
        resp = client.get("/api/recently-added",
            params={"child_id": 1},
            headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401


class TestRecentlyAddedBasic:
    """Basic happy-path scenarios."""

    def test_child_not_found(self, client, auth_headers):
        resp = client.get("/api/recently-added?child_id=999", headers=auth_headers)
        assert resp.status_code == 404

    def test_empty_when_no_videos(self, client, auth_headers, store):
        store.add_child("Alex")
        resp = client.get("/api/recently-added?child_id=1", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["videos"] == []

    def test_returns_approved_videos(self, client, auth_headers, store):
        """Approved videos appear in results."""
        # Setup: create child, add channel, add videos, approve
        # Assert: videos appear in response
        pass

    def test_excludes_pending_videos(self, client, auth_headers, store):
        """Pending (unapproved) videos should not appear."""
        pass

    def test_excludes_denied_videos(self, client, auth_headers, store):
        """Denied videos should not appear."""
        pass

    def test_excludes_blocked_channel_videos(self, client, auth_headers, store):
        """Videos from blocked channels should not appear."""
        pass


class TestRecentlyAddedOrdering:
    """Videos are ordered by approval date descending."""

    def test_ordered_by_decided_at_desc(self, client, auth_headers, store):
        """Most recently approved video appears first."""
        # Setup: approve videos at different times
        # Assert: newest approval first
        pass


class TestRecentlyAddedPagination:
    """Limit parameter controls result count."""

    def test_default_limit_20(self, client, auth_headers, store):
        """Default limit is 20 videos."""
        pass

    def test_custom_limit(self, client, auth_headers, store):
        """Custom limit param restricts results."""
        # resp = client.get("/api/recently-added?child_id=1&limit=5", headers=auth_headers)
        pass

    def test_limit_max_50(self, client, auth_headers):
        """Limit above 50 should fail validation (422)."""
        pass

    def test_limit_min_1(self, client, auth_headers):
        """Limit below 1 should fail validation (422)."""
        pass


class TestRecentlyAddedPerChild:
    """Results are per-child."""

    def test_different_children_different_results(self, client, auth_headers, store):
        """Each child sees only their own approved videos."""
        pass

    def test_missing_child_id_returns_422(self, client, auth_headers):
        """Omitting child_id returns validation error."""
        resp = client.get("/api/recently-added", headers=auth_headers)
        assert resp.status_code == 422


class TestRecentlyAddedResponseSchema:
    """Response includes video metadata and watch info."""

    def test_video_has_watch_metadata(self, client, auth_headers, store):
        """Each video dict includes watch_position, watch_duration, watch_status."""
        pass

    def test_video_has_effective_category(self, client, auth_headers, store):
        """Each video dict includes effective_category (from video or channel)."""
        pass
"""

Test plan for Issue #7: GET /api/channels/{channel_id} endpoint.

Returns channel metadata with paginated approved videos for a child.
Powers the Channel Detail screen on the tvOS app.

Expected endpoint: GET /api/channels/{channel_id}?child_id=N&offset=0&limit=24
Expected response: {
    "channel_name": "...",
    "channel_id": "UC...",
    "handle": "@...",
    "category": "...",
    "thumbnail_url": "...",
    "banner_url": "...",
    "video_count": N,
    "videos": [...],
    "has_more": bool,
    "total": N
}
"""


class TestChannelDetailAuth:
    """Auth is required for the channel detail endpoint."""

    def test_missing_auth_returns_401(self, client):
        resp = client.get("/api/channels/UCtest123456789012345678",
            params={"child_id": 1})
        assert resp.status_code == 401


class TestChannelDetailValidation:
    """Input validation for channel detail endpoint."""

    def test_invalid_channel_id_format(self, client, auth_headers):
        """Non-UC channel IDs return 400."""
        resp = client.get("/api/channels/invalid", params={"child_id": 1},
            headers=auth_headers)
        assert resp.status_code == 400

    def test_child_not_found(self, client, auth_headers):
        resp = client.get("/api/channels/UCtest123456789012345678",
            params={"child_id": 999}, headers=auth_headers)
        assert resp.status_code == 404

    def test_missing_child_id_returns_422(self, client, auth_headers):
        resp = client.get("/api/channels/UCtest123456789012345678",
            headers=auth_headers)
        assert resp.status_code == 422


class TestChannelDetailBasic:
    """Basic happy-path scenarios."""

    def test_returns_channel_metadata(self, client, auth_headers, store, mock_invidious):
        """Response includes channel name, handle, category, avatar, banner."""
        # Setup: create child with allowed channel, mock Invidious
        # Assert: response has all metadata fields
        pass

    def test_channel_without_invidious_metadata(self, client, auth_headers, store, mock_invidious):
        """If Invidious fails, channel still returns with local metadata."""
        pass

    def test_returns_paginated_videos(self, client, auth_headers, store, mock_invidious):
        """Response includes paginated approved videos for the channel."""
        # Assert: videos list, has_more, total fields
        pass

    def test_video_count_matches(self, client, auth_headers, store, mock_invidious):
        """video_count reflects total approved videos for the channel."""
        pass


class TestChannelDetailPagination:
    """Pagination for channel detail videos."""

    def test_offset_and_limit(self, client, auth_headers, store, mock_invidious):
        """Offset/limit control which videos are returned."""
        pass

    def test_has_more_true_when_more_pages(self, client, auth_headers, store, mock_invidious):
        """has_more is true when there are more videos beyond the current page."""
        pass

    def test_has_more_false_on_last_page(self, client, auth_headers, store, mock_invidious):
        """has_more is false when all videos fit in the current page."""
        pass


class TestChannelDetailPerChild:
    """Channel detail is per-child."""

    def test_only_shows_child_approved_videos(self, client, auth_headers, store, mock_invidious):
        """Only videos approved for the specified child appear."""
        pass

    def test_category_from_child_channel_list(self, client, auth_headers, store, mock_invidious):
        """Category comes from the child's channel list, not Invidious."""
        pass
