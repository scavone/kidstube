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

    def test_update_child_name(self, store):
        child = store.add_child("Alex")
        updated = store.update_child(child["id"], name="Alexander")
        assert updated is not None
        assert updated["name"] == "Alexander"
        assert updated["avatar"] == child["avatar"]

    def test_update_child_avatar(self, store):
        child = store.add_child("Alex", "👦")
        updated = store.update_child(child["id"], avatar="👧")
        assert updated is not None
        assert updated["avatar"] == "👧"
        assert updated["name"] == "Alex"

    def test_update_child_both(self, store):
        child = store.add_child("Alex", "👦")
        updated = store.update_child(child["id"], name="Sam", avatar="👧")
        assert updated is not None
        assert updated["name"] == "Sam"
        assert updated["avatar"] == "👧"

    def test_update_child_not_found(self, store):
        result = store.update_child(999, name="Ghost")
        assert result is None

    def test_update_child_name_conflict(self, store):
        store.add_child("Alex")
        child2 = store.add_child("Sam")
        result = store.update_child(child2["id"], name="Alex")
        assert result is None  # Conflict with existing name

    def test_update_child_no_change(self, store):
        child = store.add_child("Alex", "👦")
        updated = store.update_child(child["id"])
        assert updated is not None
        assert updated["name"] == "Alex"
        assert updated["avatar"] == "👦"


class TestAvatarStorage:
    def test_save_and_get_avatar(self, store):
        child = store.add_child("Alex")
        photo_data = b"\x89PNG\r\n\x1a\n fake image data"
        assert store.save_avatar(child["id"], photo_data)

        path = store.get_avatar_path(child["id"])
        assert path is not None
        assert path.read_bytes() == photo_data

        # Avatar field should now be "photo"
        updated = store.get_child(child["id"])
        assert updated["avatar"] == "photo"

    def test_save_avatar_nonexistent_child(self, store):
        assert store.save_avatar(999, b"data") is False

    def test_get_avatar_path_no_file(self, store):
        child = store.add_child("Alex")
        assert store.get_avatar_path(child["id"]) is None

    def test_delete_avatar(self, store):
        child = store.add_child("Alex")
        store.save_avatar(child["id"], b"photo data")
        assert store.get_avatar_path(child["id"]) is not None

        store.delete_avatar(child["id"])
        assert store.get_avatar_path(child["id"]) is None

    def test_delete_avatar_no_file(self, store):
        child = store.add_child("Alex")
        store.delete_avatar(child["id"])  # Should not raise

    def test_avatar_dir_created(self, store):
        avatar_dir = store.get_avatar_dir()
        assert avatar_dir.exists()
        assert avatar_dir.is_dir()


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


class TestBulkImportChannelVideos:
    def test_inserts_videos(self, store):
        child = store.add_child("Alex")
        videos = [
            {"video_id": "vid1", "title": "V1", "channel_name": "Ch", "channel_id": "UC1", "duration": 100},
            {"video_id": "vid2", "title": "V2", "channel_name": "Ch", "channel_id": "UC1", "duration": 200},
        ]
        count = store.bulk_import_channel_videos(videos, "edu", [child["id"]])
        assert count == 2
        assert store.get_video("vid1") is not None
        assert store.get_video("vid2") is not None

    def test_approves_for_all_children(self, store):
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        videos = [
            {"video_id": "vid1", "title": "V1", "channel_name": "Ch", "channel_id": "UC1"},
        ]
        store.bulk_import_channel_videos(videos, "edu", [alex["id"], sam["id"]])
        assert store.get_video_status(alex["id"], "vid1") == "approved"
        assert store.get_video_status(sam["id"], "vid1") == "approved"

    def test_skips_existing_videos(self, store):
        store.add_video("vid1", "Original Title", "Ch")
        child = store.add_child("Alex")
        videos = [
            {"video_id": "vid1", "title": "New Title", "channel_name": "Ch"},
        ]
        count = store.bulk_import_channel_videos(videos, "edu", [child["id"]])
        assert count == 0
        assert store.get_video("vid1")["title"] == "Original Title"

    def test_preserves_existing_access_decisions(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "V1", "Ch")
        store.request_video(child["id"], "vid1")
        store.update_video_status(child["id"], "vid1", "denied")
        videos = [{"video_id": "vid1", "title": "V1", "channel_name": "Ch"}]
        store.bulk_import_channel_videos(videos, "edu", [child["id"]])
        assert store.get_video_status(child["id"], "vid1") == "denied"

    def test_empty_list(self, store):
        child = store.add_child("Alex")
        count = store.bulk_import_channel_videos([], "edu", [child["id"]])
        assert count == 0

    def test_no_children(self, store):
        videos = [{"video_id": "vid1", "title": "V1", "channel_name": "Ch"}]
        count = store.bulk_import_channel_videos(videos, "edu", [])
        assert count == 0

    def test_sets_category(self, store):
        child = store.add_child("Alex")
        videos = [{"video_id": "vid1", "title": "V1", "channel_name": "Ch"}]
        store.bulk_import_channel_videos(videos, "edu", [child["id"]])
        assert store.get_video("vid1")["category"] == "edu"

    def test_skips_videos_without_id(self, store):
        child = store.add_child("Alex")
        videos = [
            {"title": "No ID", "channel_name": "Ch"},
            {"video_id": "vid1", "title": "Has ID", "channel_name": "Ch"},
        ]
        count = store.bulk_import_channel_videos(videos, "fun", [child["id"]])
        assert count == 1
        assert store.get_video("vid1") is not None


class TestChildVideoAccess:
    def test_request_pending(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Unknown Channel")
        status = store.request_video(child["id"], "vid1")
        assert status == "pending"

    def test_request_auto_approve_allowed_channel(self, store):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Good Channel", "allowed")
        store.add_video("vid1", "Title", "Good Channel")
        status = store.request_video(child["id"], "vid1")
        assert status == "auto_approved"

    def test_request_auto_deny_blocked_channel(self, store):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Bad Channel", "blocked")
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
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Good Channel", "allowed")
        assert store.is_channel_allowed(cid, "Good Channel")
        assert not store.is_channel_blocked(cid, "Good Channel")

    def test_add_and_check_blocked(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Bad Channel", "blocked")
        assert store.is_channel_blocked(cid, "Bad Channel")
        assert not store.is_channel_allowed(cid, "Bad Channel")

    def test_case_insensitive(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Test Channel", "allowed")
        assert store.is_channel_allowed(cid, "test channel")

    def test_get_channels(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Allowed 1", "allowed")
        store.add_channel(cid, "Allowed 2", "allowed")
        store.add_channel(cid, "Blocked 1", "blocked")

        allowed = store.get_channels(cid, status="allowed")
        assert len(allowed) == 2

        blocked = store.get_channels(cid, status="blocked")
        assert len(blocked) == 1

    def test_remove_channel(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Test Channel", "allowed")
        success, count = store.remove_channel(cid, "Test Channel")
        assert success
        assert count == 0
        assert not store.is_channel_allowed(cid, "Test Channel")

    def test_remove_channel_returns_video_count(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Good Channel", "allowed")
        # Add videos belonging to this channel and create access records
        store.add_video("vid_a_12345", "Video A", "Good Channel")
        store.add_video("vid_b_12345", "Video B", "Good Channel")
        store.add_video("vid_c_12345", "Video C", "Other Channel")
        store.request_video(cid, "vid_a_12345")
        store.request_video(cid, "vid_b_12345")
        store.request_video(cid, "vid_c_12345")
        success, count = store.remove_channel(cid, "Good Channel")
        assert success
        assert count == 2  # only vid_a and vid_b belong to Good Channel

    def test_remove_channel_not_found(self, store):
        child = store.add_child("Alex")
        success, count = store.remove_channel(child["id"], "Nonexistent")
        assert not success
        assert count == 0

    def test_count_channel_videos(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "TestCh", "allowed")
        store.add_video("vid_x_12345", "Video X", "TestCh")
        store.add_video("vid_y_12345", "Video Y", "TestCh")
        store.request_video(cid, "vid_x_12345")
        store.request_video(cid, "vid_y_12345")
        assert store.count_channel_videos(cid, "TestCh") == 2
        assert store.count_channel_videos(cid, "OtherCh") == 0

    def test_blocked_channels_set(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Bad 1", "blocked")
        store.add_channel(cid, "Bad 2", "blocked")
        store.add_channel(cid, "Good 1", "allowed")

        blocked = store.get_blocked_channels_set(cid)
        assert blocked == {"bad 1", "bad 2"}

    def test_per_child_independence(self, store):
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.add_channel(alex["id"], "Fun Channel", "allowed")
        store.add_channel(sam["id"], "Fun Channel", "blocked")
        assert store.is_channel_allowed(alex["id"], "Fun Channel")
        assert store.is_channel_blocked(sam["id"], "Fun Channel")
        assert not store.is_channel_allowed(sam["id"], "Fun Channel")


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


class TestRequestVideoAtomic:
    """Tests for the atomic INSERT OR IGNORE behavior of request_video (#27)."""

    def test_concurrent_requests_are_idempotent(self, store):
        """Two calls for the same child+video return consistent status."""
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        s1 = store.request_video(child["id"], "vid1")
        s2 = store.request_video(child["id"], "vid1")
        assert s1 == "pending"
        assert s2 == "pending"

    def test_auto_approved_returns_correctly(self, store):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Safe Channel", "allowed")
        store.add_video("vid1", "Title", "Safe Channel")
        s1 = store.request_video(child["id"], "vid1")
        assert s1 == "auto_approved"
        # Second call should return existing status (approved was stored)
        s2 = store.request_video(child["id"], "vid1")
        assert s2 == "approved"

    def test_denied_channel_stores_denied(self, store):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Bad Channel", "blocked")
        store.add_video("vid1", "Title", "Bad Channel")
        s1 = store.request_video(child["id"], "vid1")
        assert s1 == "denied"
        # Second call returns existing denied status
        s2 = store.request_video(child["id"], "vid1")
        assert s2 == "denied"

    def test_no_video_record_still_works(self, store):
        """request_video works even if video isn't in the videos table yet."""
        child = store.add_child("Alex")
        status = store.request_video(child["id"], "nonexistent_vid")
        assert status == "pending"
