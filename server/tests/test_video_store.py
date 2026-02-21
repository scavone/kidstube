"""Tests for data/video_store.py — SQLite data layer with multi-child support."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from data.video_store import VideoStore


@pytest.fixture
def store(tmp_path):
    """Create a fresh VideoStore with an in-memory-like temp DB for each test."""
    db_path = str(tmp_path / "test.db")
    s = VideoStore(db_path)
    yield s
    s.close()


class TestChildProfiles:
    def test_add_child(self, store):
        child = store.add_child("Alex", "👦")
        assert child is not None
        assert child["name"] == "Alex"
        assert child["avatar"] == "👦"
        assert child["id"] > 0

    def test_add_duplicate_child_returns_none(self, store):
        store.add_child("Alex")
        result = store.add_child("Alex")
        assert result is None

    def test_add_child_case_insensitive(self, store):
        store.add_child("Alex")
        result = store.add_child("alex")
        assert result is None

    def test_get_children(self, store):
        store.add_child("Alex")
        store.add_child("Sam")
        children = store.get_children()
        assert len(children) == 2
        names = [c["name"] for c in children]
        assert "Alex" in names
        assert "Sam" in names

    def test_get_child(self, store):
        created = store.add_child("Alex")
        found = store.get_child(created["id"])
        assert found["name"] == "Alex"

    def test_get_child_not_found(self, store):
        assert store.get_child(999) is None

    def test_get_child_by_name(self, store):
        store.add_child("Alex")
        found = store.get_child_by_name("alex")  # case-insensitive
        assert found is not None
        assert found["name"] == "Alex"

    def test_remove_child(self, store):
        child = store.add_child("Alex")
        assert store.remove_child(child["id"])
        assert store.get_child(child["id"]) is None

    def test_remove_child_cascades_settings(self, store):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")
        store.remove_child(child["id"])
        assert store.get_child_setting(child["id"], "daily_limit_minutes") == ""


class TestChildSettings:
    def test_set_and_get(self, store):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "90")
        assert store.get_child_setting(child["id"], "daily_limit_minutes") == "90"

    def test_get_default(self, store):
        child = store.add_child("Alex")
        assert store.get_child_setting(child["id"], "nonexistent", "default") == "default"

    def test_upsert(self, store):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "key", "value1")
        store.set_child_setting(child["id"], "key", "value2")
        assert store.get_child_setting(child["id"], "key") == "value2"

    def test_get_all_settings(self, store):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "a", "1")
        store.set_child_setting(child["id"], "b", "2")
        settings = store.get_child_settings(child["id"])
        assert settings == {"a": "1", "b": "2"}


class TestVideos:
    def test_add_video(self, store):
        video = store.add_video(
            video_id="abc12345678",
            title="Test Video",
            channel_name="Test Channel",
            channel_id="UCTEST",
            duration=300,
        )
        assert video["video_id"] == "abc12345678"
        assert video["title"] == "Test Video"

    def test_add_duplicate_returns_existing(self, store):
        store.add_video("abc12345678", "Title 1", "Ch 1")
        video = store.add_video("abc12345678", "Title 2", "Ch 2")
        assert video["title"] == "Title 1"  # Original preserved

    def test_get_video(self, store):
        store.add_video("abc12345678", "Title", "Channel")
        video = store.get_video("abc12345678")
        assert video is not None
        assert video["title"] == "Title"

    def test_get_video_not_found(self, store):
        assert store.get_video("nonexistent") is None


class TestChildVideoAccess:
    def test_request_pending(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Unknown Channel")
        status = store.request_video(child["id"], "vid1")
        assert status == "pending"

    def test_request_auto_approve_allowed_channel(self, store):
        child = store.add_child("Alex")
        store.add_channel("Good Channel", "allowed")
        store.add_video("vid1", "Title", "Good Channel")
        status = store.request_video(child["id"], "vid1")
        assert status == "auto_approved"

    def test_request_auto_deny_blocked_channel(self, store):
        child = store.add_child("Alex")
        store.add_channel("Bad Channel", "blocked")
        store.add_video("vid1", "Title", "Bad Channel")
        status = store.request_video(child["id"], "vid1")
        assert status == "denied"

    def test_request_idempotent(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")
        status = store.request_video(child["id"], "vid1")
        assert status == "pending"  # Returns existing status

    def test_per_child_independence(self, store):
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.add_video("vid1", "Title", "Channel")

        store.request_video(alex["id"], "vid1")
        store.update_video_status(alex["id"], "vid1", "approved")

        # Sam hasn't requested yet
        assert store.get_video_status(sam["id"], "vid1") is None

    def test_get_video_status(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")
        assert store.get_video_status(child["id"], "vid1") == "pending"

    def test_update_video_status(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")
        assert store.update_video_status(child["id"], "vid1", "approved")
        assert store.get_video_status(child["id"], "vid1") == "approved"

    def test_get_pending_requests_all(self, store):
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.add_video("vid1", "Title 1", "Channel")
        store.add_video("vid2", "Title 2", "Channel")
        store.request_video(alex["id"], "vid1")
        store.request_video(sam["id"], "vid2")

        pending = store.get_pending_requests()
        assert len(pending) == 2

    def test_get_pending_requests_by_child(self, store):
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.add_video("vid1", "Title 1", "Channel")
        store.add_video("vid2", "Title 2", "Channel")
        store.request_video(alex["id"], "vid1")
        store.request_video(sam["id"], "vid2")

        pending = store.get_pending_requests(child_id=alex["id"])
        assert len(pending) == 1
        assert pending[0]["video_id"] == "vid1"

    def test_get_approved_videos(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Approved", "Channel")
        store.add_video("vid2", "Pending", "Channel")
        store.request_video(child["id"], "vid1")
        store.request_video(child["id"], "vid2")
        store.update_video_status(child["id"], "vid1", "approved")

        videos, total = store.get_approved_videos(child["id"])
        assert total == 1
        assert videos[0]["video_id"] == "vid1"


class TestWatchTracking:
    def test_record_and_get_daily_minutes(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.record_watch_seconds("vid1", child["id"], 120)
        store.record_watch_seconds("vid1", child["id"], 60)

        minutes = store.get_daily_watch_minutes(child["id"], "2099-01-01")
        # Without UTC bounds for today, this won't match the auto-generated dates
        # Let's query without bounds to test the accumulation
        from utils import get_today_str, get_day_utc_bounds
        today = get_today_str()
        bounds = get_day_utc_bounds(today)
        minutes = store.get_daily_watch_minutes(child["id"], today, utc_bounds=bounds)
        assert minutes == 3.0  # 180 seconds = 3 minutes

    def test_per_child_tracking(self, store):
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.add_video("vid1", "Title", "Channel")
        store.record_watch_seconds("vid1", alex["id"], 120)
        store.record_watch_seconds("vid1", sam["id"], 60)

        from utils import get_today_str, get_day_utc_bounds
        today = get_today_str()
        bounds = get_day_utc_bounds(today)

        assert store.get_daily_watch_minutes(alex["id"], today, utc_bounds=bounds) == 2.0
        assert store.get_daily_watch_minutes(sam["id"], today, utc_bounds=bounds) == 1.0

    def test_daily_breakdown(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Video 1", "Ch1")
        store.add_video("vid2", "Video 2", "Ch2")
        store.record_watch_seconds("vid1", child["id"], 300)
        store.record_watch_seconds("vid2", child["id"], 120)

        from utils import get_today_str, get_day_utc_bounds
        today = get_today_str()
        bounds = get_day_utc_bounds(today)

        breakdown = store.get_daily_watch_breakdown(child["id"], today, utc_bounds=bounds)
        assert len(breakdown) == 2
        assert breakdown[0]["minutes"] == 5.0  # vid1: 300s
        assert breakdown[1]["minutes"] == 2.0  # vid2: 120s


class TestChannels:
    def test_add_and_check_allowed(self, store):
        store.add_channel("Good Channel", "allowed")
        assert store.is_channel_allowed("Good Channel")
        assert not store.is_channel_blocked("Good Channel")

    def test_add_and_check_blocked(self, store):
        store.add_channel("Bad Channel", "blocked")
        assert store.is_channel_blocked("Bad Channel")
        assert not store.is_channel_allowed("Bad Channel")

    def test_case_insensitive(self, store):
        store.add_channel("Test Channel", "allowed")
        assert store.is_channel_allowed("test channel")

    def test_get_channels(self, store):
        store.add_channel("Allowed 1", "allowed")
        store.add_channel("Allowed 2", "allowed")
        store.add_channel("Blocked 1", "blocked")

        allowed = store.get_channels(status="allowed")
        assert len(allowed) == 2

        blocked = store.get_channels(status="blocked")
        assert len(blocked) == 1

    def test_remove_channel(self, store):
        store.add_channel("Test Channel", "allowed")
        assert store.remove_channel("Test Channel")
        assert not store.is_channel_allowed("Test Channel")

    def test_blocked_channels_set(self, store):
        store.add_channel("Bad 1", "blocked")
        store.add_channel("Bad 2", "blocked")
        store.add_channel("Good 1", "allowed")

        blocked = store.get_blocked_channels_set()
        assert blocked == {"bad 1", "bad 2"}


class TestWordFilters:
    def test_add_and_get(self, store):
        assert store.add_word_filter("badword")
        words = store.get_word_filters()
        assert "badword" in words

    def test_duplicate_returns_false(self, store):
        store.add_word_filter("test")
        assert not store.add_word_filter("test")

    def test_remove(self, store):
        store.add_word_filter("test")
        assert store.remove_word_filter("test")
        assert "test" not in store.get_word_filters()

    def test_get_set(self, store):
        store.add_word_filter("Word1")
        store.add_word_filter("Word2")
        s = store.get_word_filters_set()
        assert s == {"word1", "word2"}


class TestGlobalSettings:
    def test_set_and_get(self, store):
        store.set_setting("test_key", "test_value")
        assert store.get_setting("test_key") == "test_value"

    def test_get_default(self, store):
        assert store.get_setting("missing", "default") == "default"

    def test_upsert(self, store):
        store.set_setting("key", "v1")
        store.set_setting("key", "v2")
        assert store.get_setting("key") == "v2"


class TestStats:
    def test_stats_all(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "T1", "Ch")
        store.add_video("vid2", "T2", "Ch")
        store.add_video("vid3", "T3", "Ch")
        store.request_video(child["id"], "vid1")
        store.request_video(child["id"], "vid2")
        store.request_video(child["id"], "vid3")
        store.update_video_status(child["id"], "vid1", "approved")
        store.update_video_status(child["id"], "vid2", "denied")

        stats = store.get_stats()
        assert stats["total"] == 3
        assert stats["approved"] == 1
        assert stats["denied"] == 1
        assert stats["pending"] == 1

    def test_stats_per_child(self, store):
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.add_video("vid1", "T1", "Ch")
        store.request_video(alex["id"], "vid1")
        store.request_video(sam["id"], "vid1")
        store.update_video_status(alex["id"], "vid1", "approved")

        alex_stats = store.get_stats(child_id=alex["id"])
        assert alex_stats["approved"] == 1
        assert alex_stats["pending"] == 0

        sam_stats = store.get_stats(child_id=sam["id"])
        assert sam_stats["pending"] == 1
        assert sam_stats["approved"] == 0
