"""Test plan for Issue #3: Home screen channels endpoint.

Tests the new API endpoint that returns approved channels for a given child,
each with their most recent video, to power the home screen channel row
and featured banner.

Expected endpoint: GET /api/home/channels?child_id=N
Expected response: {
    "channels": [
        {
            "channel_id": "UC...",
            "channel_name": "...",
            "handle": "@...",
            "avatar_url": "...",          # channel thumbnail/avatar
            "banner_url": "...",          # authorBanner from Invidious (for featured banner)
            "category": "...",
            "latest_video": {
                "video_id": "...",
                "title": "...",
                "thumbnail_url": "...",
                "duration": 180,
                "published": 1700000000   # unix timestamp for ordering
            }
        }
    ]
}
Channels ordered by latest_video.published descending (most recent first).
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


# ── Fixtures (same pattern as test_api.py) ────────────────────────

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


def _seed_child(store, name="Alex"):
    """Create a child profile and return its ID."""
    return store.add_child(name)


def _seed_channel(store, child_id, channel_name, channel_id, category=None):
    """Add an allowed channel for a child."""
    store.add_channel(
        child_id, channel_name, "allowed",
        channel_id=channel_id, category=category,
    )


def _seed_video(store, child_id, video_id, title, channel_name, channel_id=None):
    """Insert a video and grant access for a child."""
    store.add_video(video_id, title, channel_name, channel_id=channel_id)
    store.request_video(child_id, video_id)


# ── Test Plan ─────────────────────────────────────────────────────
# The tests below are stubs outlining what will be validated.
# Actual assertions will be filled in during Phase 2 review
# once the endpoint implementation is complete.

class TestHomeChannelsAuth:
    """Auth is required for the home channels endpoint."""

    def test_missing_auth_returns_401(self, client):
        """Endpoint must reject unauthenticated requests."""
        # TODO: uncomment once endpoint exists
        # resp = client.get("/api/home/channels", params={"child_id": 1})
        # assert resp.status_code == 401
        pass

    def test_wrong_key_returns_401(self, client):
        """Endpoint must reject wrong API key."""
        # resp = client.get("/api/home/channels",
        #     params={"child_id": 1},
        #     headers={"Authorization": "Bearer wrong"})
        # assert resp.status_code == 401
        pass


class TestHomeChannelsBasic:
    """Basic happy-path responses."""

    def test_returns_channels_for_child(self, client, auth_headers, store):
        """Each approved channel for the child appears in the response."""
        # Setup: create child, add 2 allowed channels with videos
        # Assert: response contains both channels
        # Assert: each channel has channel_id, channel_name, latest_video
        pass

    def test_empty_when_no_channels(self, client, auth_headers, store):
        """A child with no approved channels returns an empty list."""
        # Setup: create child with no channels
        # Assert: response.channels == []
        pass

    def test_only_allowed_channels_included(self, client, auth_headers, store):
        """Blocked channels must NOT appear in the response."""
        # Setup: add one allowed and one blocked channel
        # Assert: only the allowed channel appears
        pass


class TestHomeChannelsPerChild:
    """Channels are per-child — child isolation."""

    def test_different_children_different_channels(self, client, auth_headers, store):
        """Each child sees only their own approved channels."""
        # Setup: child A has channel X, child B has channel Y
        # Assert: querying child_id=A returns only X
        # Assert: querying child_id=B returns only Y
        pass

    def test_invalid_child_id_returns_404(self, client, auth_headers):
        """Querying a non-existent child_id returns 404."""
        # resp = client.get("/api/home/channels",
        #     params={"child_id": 999}, headers=auth_headers)
        # assert resp.status_code == 404
        pass

    def test_missing_child_id_returns_422(self, client, auth_headers):
        """Omitting child_id returns 422 (validation error)."""
        # resp = client.get("/api/home/channels", headers=auth_headers)
        # assert resp.status_code == 422
        pass


class TestHomeChannelsOrdering:
    """Channels are ordered by most recently published video."""

    def test_ordered_by_latest_video_publish_date(self, client, auth_headers, store):
        """Channel with the newest video appears first."""
        # Setup: channel A has video published 2025-01-01
        #        channel B has video published 2025-02-01
        # Assert: channel B appears before channel A in the list
        pass

    def test_channel_without_videos_appears_last(self, client, auth_headers, store):
        """A channel with no videos should sort to the end."""
        # Setup: channel A has videos, channel B has none
        # Assert: channel A appears before channel B
        pass


class TestHomeChannelsLatestVideo:
    """Each channel includes its most recent video."""

    def test_latest_video_fields(self, client, auth_headers, store):
        """The latest_video object contains required fields."""
        # Assert: latest_video has video_id, title, thumbnail_url, duration
        pass

    def test_latest_video_is_most_recent(self, client, auth_headers, store):
        """When a channel has multiple videos, only the newest is returned."""
        # Setup: channel has 3 videos with different publish dates
        # Assert: latest_video.video_id matches the most recent one
        pass

    def test_channel_with_no_videos_has_null_latest(self, client, auth_headers, store):
        """A channel with no approved videos has latest_video: null."""
        # Setup: channel exists but has no video access records
        # Assert: latest_video is None/null
        pass


class TestHomeChannelsBannerData:
    """Banner/avatar URL data for the featured banner."""

    def test_channel_has_avatar_url(self, client, auth_headers, store):
        """Each channel includes an avatar_url for the channel row."""
        # Will depend on how backend fetches this — possibly from Invidious
        # or from a stored field
        pass

    def test_channel_has_banner_url(self, client, auth_headers, store):
        """Each channel includes a banner_url for the featured banner."""
        # Invidious authorBanners provides this data
        pass


class TestHomeChannelsResponseSchema:
    """Response schema validation."""

    def test_response_has_channels_key(self, client, auth_headers, store):
        """Top-level response must have a 'channels' key with a list."""
        # child_id = _seed_child(store)
        # resp = client.get("/api/home/channels",
        #     params={"child_id": child_id}, headers=auth_headers)
        # assert "channels" in resp.json()
        # assert isinstance(resp.json()["channels"], list)
        pass

    def test_channel_object_schema(self, client, auth_headers, store):
        """Each channel object has the expected keys."""
        # Expected keys: channel_id, channel_name, handle, avatar_url,
        #                banner_url, category, latest_video
        pass

    def test_latest_video_object_schema(self, client, auth_headers, store):
        """The latest_video sub-object has the expected keys."""
        # Expected keys: video_id, title, thumbnail_url, duration, published
        pass
