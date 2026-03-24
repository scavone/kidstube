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

        videos, total, _ = store.get_approved_videos(child["id"])
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


class TestChannelsWithLatestVideo:
    def test_empty_channels(self, store):
        child = store.add_child("Alex")
        result = store.get_channels_with_latest_video(child["id"])
        assert result == []

    def test_channel_with_no_videos(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Empty Channel", "allowed", channel_id="UCtest1234567890123456")
        result = store.get_channels_with_latest_video(cid)
        assert len(result) == 1
        assert result[0]["channel_name"] == "Empty Channel"
        assert result[0]["latest_video"] is None

    def test_channel_with_latest_video(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Fun Channel", "allowed", channel_id="UCfun12345678901234567")
        # Add videos with different published times
        store.add_video("vid_old1234", "Old Video", "Fun Channel",
                        channel_id="UCfun12345678901234567", published_at=1000)
        store.add_video("vid_new1234", "New Video", "Fun Channel",
                        channel_id="UCfun12345678901234567", published_at=2000)
        store.request_video(cid, "vid_old1234")
        store.request_video(cid, "vid_new1234")

        result = store.get_channels_with_latest_video(cid)
        assert len(result) == 1
        assert result[0]["latest_video"]["video_id"] == "vid_new1234"
        assert result[0]["latest_video"]["title"] == "New Video"
        assert result[0]["latest_video"]["published_at"] == 2000

    def test_ordered_by_latest_published(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Old Channel", "allowed", channel_id="UCold12345678901234567")
        store.add_channel(cid, "New Channel", "allowed", channel_id="UCnew12345678901234567")

        store.add_video("vid_old_ch01", "Old Ch Video", "Old Channel",
                        channel_id="UCold12345678901234567", published_at=1000)
        store.add_video("vid_new_ch01", "New Ch Video", "New Channel",
                        channel_id="UCnew12345678901234567", published_at=3000)
        store.request_video(cid, "vid_old_ch01")
        store.request_video(cid, "vid_new_ch01")

        result = store.get_channels_with_latest_video(cid)
        assert len(result) == 2
        assert result[0]["channel_name"] == "New Channel"
        assert result[1]["channel_name"] == "Old Channel"

    def test_excludes_blocked_channels(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Good Channel", "allowed")
        store.add_channel(cid, "Bad Channel", "blocked")

        result = store.get_channels_with_latest_video(cid)
        assert len(result) == 1
        assert result[0]["channel_name"] == "Good Channel"

    def test_per_child_isolation(self, store):
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.add_channel(alex["id"], "Alex Channel", "allowed")
        store.add_channel(sam["id"], "Sam Channel", "allowed")

        alex_result = store.get_channels_with_latest_video(alex["id"])
        sam_result = store.get_channels_with_latest_video(sam["id"])
        assert len(alex_result) == 1
        assert alex_result[0]["channel_name"] == "Alex Channel"
        assert len(sam_result) == 1
        assert sam_result[0]["channel_name"] == "Sam Channel"

    def test_only_approved_videos_included(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Test Channel", "allowed", channel_id="UCtst12345678901234567")

        store.add_video("vid_approv1", "Approved", "Test Channel",
                        channel_id="UCtst12345678901234567", published_at=1000)
        store.add_video("vid_denied1", "Denied", "Test Channel",
                        channel_id="UCtst12345678901234567", published_at=2000)
        store.request_video(cid, "vid_approv1")  # auto-approved (channel allowed)
        store.request_video(cid, "vid_denied1")  # auto-approved
        store.update_video_status(cid, "vid_denied1", "denied")

        result = store.get_channels_with_latest_video(cid)
        assert len(result) == 1
        # Should pick the approved one, not the denied one
        assert result[0]["latest_video"]["video_id"] == "vid_approv1"


class TestRecentlyAddedVideos:
    def test_empty(self, store):
        child = store.add_child("Alex")
        result = store.get_recently_added_videos(child["id"])
        assert result == []

    def test_ordered_by_approval_date(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Ch", "allowed")
        store.add_video("vid_first123", "First", "Ch")
        store.request_video(cid, "vid_first123")  # approved first
        store.add_video("vid_secnd123", "Second", "Ch")
        store.request_video(cid, "vid_secnd123")  # approved second

        result = store.get_recently_added_videos(cid)
        assert len(result) == 2
        # Most recently approved should come first
        assert result[0]["video_id"] == "vid_secnd123"
        assert result[1]["video_id"] == "vid_first123"

    def test_only_approved_videos(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_video("vid_apprvd1", "Approved", "Ch")
        store.add_video("vid_pendng1", "Pending", "Ch")
        store.request_video(cid, "vid_apprvd1")
        store.request_video(cid, "vid_pendng1")
        store.update_video_status(cid, "vid_apprvd1", "approved")
        # vid_pendng1 stays pending

        result = store.get_recently_added_videos(cid)
        assert len(result) == 1
        assert result[0]["video_id"] == "vid_apprvd1"

    def test_respects_limit(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "Ch", "allowed")
        for i in range(5):
            vid = f"vid_{i:07d}"
            store.add_video(vid, f"Video {i}", "Ch")
            store.request_video(cid, vid)

        result = store.get_recently_added_videos(cid, limit=3)
        assert len(result) == 3


class TestChannelVideoCount:
    def test_count(self, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_video("vid_a_12345", "A", "Ch", channel_id="UCtest1234567890123456")
        store.add_video("vid_b_12345", "B", "Ch", channel_id="UCtest1234567890123456")
        store.add_video("vid_c_12345", "C", "Other", channel_id="UCothr1234567890123456")
        store.request_video(cid, "vid_a_12345")
        store.request_video(cid, "vid_b_12345")
        store.request_video(cid, "vid_c_12345")
        store.update_video_status(cid, "vid_a_12345", "approved")
        store.update_video_status(cid, "vid_b_12345", "approved")
        store.update_video_status(cid, "vid_c_12345", "approved")

        assert store.get_channel_video_count(cid, "UCtest1234567890123456") == 2
        assert store.get_channel_video_count(cid, "UCothr1234567890123456") == 1
        assert store.get_channel_video_count(cid, "UCnone1234567890123456") == 0


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


class TestWatchPosition:
    def test_save_and_get_position(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")

        result = store.save_watch_position(child["id"], "vid1", 120, 600)
        assert result == "in_progress"
        pos = store.get_watch_position(child["id"], "vid1")
        assert pos is not None
        assert pos["watch_position"] == 120
        assert pos["watch_duration"] == 600
        assert pos["last_watched_at"] is not None

    def test_save_position_updates_existing(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")

        store.save_watch_position(child["id"], "vid1", 60, 600)
        store.save_watch_position(child["id"], "vid1", 120, 600)
        pos = store.get_watch_position(child["id"], "vid1")
        assert pos["watch_position"] == 120

    def test_save_position_no_access_row(self, store):
        child = store.add_child("Alex")
        # No video access row exists
        result = store.save_watch_position(child["id"], "vid1", 120, 600)
        assert result is None

    def test_get_position_no_access_row(self, store):
        child = store.add_child("Alex")
        pos = store.get_watch_position(child["id"], "vid1")
        assert pos is None

    def test_get_position_default_zero(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")

        pos = store.get_watch_position(child["id"], "vid1")
        assert pos is not None
        assert pos["watch_position"] == 0
        assert pos["watch_duration"] == 0
        assert pos["last_watched_at"] is None

    def test_clear_position(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")
        store.save_watch_position(child["id"], "vid1", 120, 600)

        assert store.clear_watch_position(child["id"], "vid1")
        pos = store.get_watch_position(child["id"], "vid1")
        assert pos["watch_position"] == 0
        assert pos["watch_duration"] == 0
        assert pos["last_watched_at"] is None

    def test_per_child_independence(self, store):
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(alex["id"], "vid1")
        store.request_video(sam["id"], "vid1")

        store.save_watch_position(alex["id"], "vid1", 120, 600)
        store.save_watch_position(sam["id"], "vid1", 300, 600)

        alex_pos = store.get_watch_position(alex["id"], "vid1")
        sam_pos = store.get_watch_position(sam["id"], "vid1")
        assert alex_pos["watch_position"] == 120
        assert sam_pos["watch_position"] == 300

    def test_position_in_approved_videos(self, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")
        store.update_video_status(child["id"], "vid1", "approved")
        store.save_watch_position(child["id"], "vid1", 120, 600)

        videos, total, _ = store.get_approved_videos(child["id"])
        assert total == 1
        assert videos[0]["watch_position"] == 120
        assert videos[0]["watch_duration"] == 600
        assert videos[0]["last_watched_at"] is not None


class TestChannelRequests:
    def test_request_channel_pending(self, store):
        child = store.add_child("Alex")
        status = store.request_channel(child["id"], "UCabcdef12345678901234AB", "Test Channel")
        assert status == "pending"

    def test_request_channel_already_allowed(self, store):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Test Channel", "allowed")
        status = store.request_channel(child["id"], "UCabcdef12345678901234AB", "Test Channel")
        assert status == "approved"

    def test_request_channel_already_blocked(self, store):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Test Channel", "blocked")
        status = store.request_channel(child["id"], "UCabcdef12345678901234AB", "Test Channel")
        assert status == "denied"

    def test_request_channel_idempotent(self, store):
        child = store.add_child("Alex")
        status1 = store.request_channel(child["id"], "UCabcdef12345678901234AB", "Test Channel")
        status2 = store.request_channel(child["id"], "UCabcdef12345678901234AB", "Test Channel")
        assert status1 == "pending"
        assert status2 == "pending"

    def test_get_channel_request_status(self, store):
        child = store.add_child("Alex")
        assert store.get_channel_request_status(child["id"], "UCabcdef12345678901234AB") is None
        store.request_channel(child["id"], "UCabcdef12345678901234AB", "Test Channel")
        assert store.get_channel_request_status(child["id"], "UCabcdef12345678901234AB") == "pending"

    def test_update_channel_request_status(self, store):
        child = store.add_child("Alex")
        store.request_channel(child["id"], "UCabcdef12345678901234AB", "Test Channel")
        updated = store.update_channel_request_status(child["id"], "UCabcdef12345678901234AB", "approved")
        assert updated is True
        assert store.get_channel_request_status(child["id"], "UCabcdef12345678901234AB") == "approved"

    def test_get_pending_channel_request(self, store):
        child = store.add_child("Alex")
        store.request_channel(child["id"], "UCabcdef12345678901234AB", "Test Channel")
        req = store.get_pending_channel_request(child["id"], "UCabcdef12345678901234AB")
        assert req is not None
        assert req["channel_name"] == "Test Channel"
        assert req["status"] == "pending"

    def test_channel_request_cascade_on_child_delete(self, store):
        child = store.add_child("Alex")
        store.request_channel(child["id"], "UCabcdef12345678901234AB", "Test Channel")
        store.remove_child(child["id"])
        assert store.get_channel_request_status(child["id"], "UCabcdef12345678901234AB") is None


class TestAutoComplete:
    def test_auto_complete_triggers(self, store):
        """Position near end (within threshold) marks as watched, clears position."""
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")

        result = store.save_watch_position(child["id"], "vid1", 580, 600, auto_complete_threshold=30)
        assert result == "watched"
        pos = store.get_watch_position(child["id"], "vid1")
        assert pos["watch_position"] == 0
        assert pos["watch_status"] == "watched"

    def test_auto_complete_does_not_trigger(self, store):
        """Position far from end stays in_progress."""
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")

        result = store.save_watch_position(child["id"], "vid1", 550, 600, auto_complete_threshold=30)
        assert result == "in_progress"
        pos = store.get_watch_position(child["id"], "vid1")
        assert pos["watch_position"] == 550
        assert pos["watch_status"] == "in_progress"

    def test_auto_complete_threshold_boundary(self, store):
        """Position exactly at duration-threshold triggers auto-complete."""
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")

        result = store.save_watch_position(child["id"], "vid1", 570, 600, auto_complete_threshold=30)
        assert result == "watched"

    def test_auto_complete_preserves_duration(self, store):
        """After auto-complete, watch_duration is still set for client reference."""
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")

        store.save_watch_position(child["id"], "vid1", 590, 600)
        pos = store.get_watch_position(child["id"], "vid1")
        assert pos["watch_duration"] == 600
        assert pos["watch_status"] == "watched"

    def test_watch_status_in_approved_videos(self, store):
        """get_approved_videos includes watch_status."""
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")
        store.update_video_status(child["id"], "vid1", "approved")
        store.save_watch_position(child["id"], "vid1", 120, 600)

        videos, total, _ = store.get_approved_videos(child["id"])
        assert total == 1
        assert videos[0]["watch_status"] == "in_progress"

    def test_set_watch_status(self, store):
        """Manual set/clear of watch_status."""
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")
        store.save_watch_position(child["id"], "vid1", 120, 600)

        # Mark as watched manually
        assert store.set_watch_status(child["id"], "vid1", "watched")
        pos = store.get_watch_position(child["id"], "vid1")
        assert pos["watch_status"] == "watched"

        # Clear (mark as unwatched)
        assert store.set_watch_status(child["id"], "vid1", "")
        pos = store.get_watch_position(child["id"], "vid1")
        assert pos["watch_status"] is None
        assert pos["watch_position"] == 0
        assert pos["watch_duration"] == 0


class TestChildPin:
    """Tests for child profile PIN management."""

    def test_set_and_verify_pin(self, store):
        child = store.add_child("Alex")
        store.set_child_pin(child["id"], "1234")
        assert store.verify_child_pin(child["id"], "1234") is True

    def test_wrong_pin_fails(self, store):
        child = store.add_child("Alex")
        store.set_child_pin(child["id"], "1234")
        assert store.verify_child_pin(child["id"], "5678") is False

    def test_has_child_pin(self, store):
        child = store.add_child("Alex")
        assert store.has_child_pin(child["id"]) is False
        store.set_child_pin(child["id"], "1234")
        assert store.has_child_pin(child["id"]) is True

    def test_delete_child_pin(self, store):
        child = store.add_child("Alex")
        store.set_child_pin(child["id"], "1234")
        assert store.delete_child_pin(child["id"]) is True
        assert store.has_child_pin(child["id"]) is False

    def test_delete_nonexistent_pin(self, store):
        child = store.add_child("Alex")
        assert store.delete_child_pin(child["id"]) is False

    def test_verify_no_pin_returns_false(self, store):
        child = store.add_child("Alex")
        assert store.verify_child_pin(child["id"], "1234") is False

    def test_change_pin(self, store):
        child = store.add_child("Alex")
        store.set_child_pin(child["id"], "1234")
        store.set_child_pin(child["id"], "5678")
        assert store.verify_child_pin(child["id"], "1234") is False
        assert store.verify_child_pin(child["id"], "5678") is True

    def test_pin_uses_salt(self, store):
        """Each set_child_pin should use a unique salt."""
        child = store.add_child("Alex")
        store.set_child_pin(child["id"], "1234")
        stored1 = store.get_child_setting(child["id"], "pin")
        store.set_child_pin(child["id"], "1234")
        stored2 = store.get_child_setting(child["id"], "pin")
        # Different salts → different stored values
        assert stored1 != stored2
        # But both still verify
        assert store.verify_child_pin(child["id"], "1234") is True

    def test_pin_independent_per_child(self, store):
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.set_child_pin(alex["id"], "1111")
        store.set_child_pin(sam["id"], "2222")
        assert store.verify_child_pin(alex["id"], "1111") is True
        assert store.verify_child_pin(alex["id"], "2222") is False
        assert store.verify_child_pin(sam["id"], "2222") is True
        assert store.verify_child_pin(sam["id"], "1111") is False

    def test_pin_deleted_with_child(self, store):
        """PIN should be deleted when child is removed (CASCADE)."""
        child = store.add_child("Alex")
        store.set_child_pin(child["id"], "1234")
        store.remove_child(child["id"])
        assert store.has_child_pin(child["id"]) is False


class TestPairing:
    """Tests for pairing session and device management."""

    def test_create_pairing_session(self, store):
        session = store.create_pairing_session(device_name="Test TV")
        assert session["token"]
        assert len(session["pin"]) == 6
        assert session["pin"].isdigit()
        assert session["status"] == "pending"
        assert session["device_name"] == "Test TV"

    def test_get_pairing_session(self, store):
        session = store.create_pairing_session()
        fetched = store.get_pairing_session(session["token"])
        assert fetched is not None
        assert fetched["token"] == session["token"]

    def test_get_pairing_session_not_found(self, store):
        assert store.get_pairing_session("nonexistent") is None

    def test_get_pairing_session_by_pin(self, store):
        session = store.create_pairing_session()
        found = store.get_pairing_session_by_pin(session["pin"])
        assert found is not None
        assert found["token"] == session["token"]

    def test_get_pairing_session_by_pin_not_found(self, store):
        assert store.get_pairing_session_by_pin("000000") is None

    def test_confirm_pairing(self, store):
        session = store.create_pairing_session(device_name="Living Room")
        device = store.confirm_pairing(session["token"])
        assert device is not None
        assert device["device_name"] == "Living Room"
        assert device["api_key"]
        assert device["is_active"] == 1

    def test_confirm_pairing_custom_name(self, store):
        session = store.create_pairing_session(device_name="Old Name")
        device = store.confirm_pairing(session["token"], device_name="New Name")
        assert device["device_name"] == "New Name"

    def test_confirm_pairing_default_name(self, store):
        session = store.create_pairing_session()
        device = store.confirm_pairing(session["token"])
        assert device["device_name"] == "Apple TV"

    def test_confirm_pairing_updates_session_status(self, store):
        session = store.create_pairing_session()
        store.confirm_pairing(session["token"])
        updated = store.get_pairing_session(session["token"])
        assert updated["status"] == "confirmed"

    def test_confirm_already_confirmed_returns_none(self, store):
        session = store.create_pairing_session()
        store.confirm_pairing(session["token"])
        assert store.confirm_pairing(session["token"]) is None

    def test_set_and_get_device_key(self, store):
        session = store.create_pairing_session()
        device = store.confirm_pairing(session["token"])
        store.set_pairing_device_key(session["token"], device["api_key"])
        updated = store.get_pairing_session(session["token"])
        assert updated["device_api_key"] == device["api_key"]

    def test_get_paired_devices(self, store):
        s1 = store.create_pairing_session(device_name="TV 1")
        s2 = store.create_pairing_session(device_name="TV 2")
        store.confirm_pairing(s1["token"])
        store.confirm_pairing(s2["token"])
        devices = store.get_paired_devices()
        assert len(devices) == 2

    def test_revoke_device(self, store):
        session = store.create_pairing_session()
        device = store.confirm_pairing(session["token"])
        assert store.revoke_device(device["id"])
        # After revoke, get_device_by_api_key returns None
        assert store.get_device_by_api_key(device["api_key"]) is None

    def test_revoke_nonexistent(self, store):
        assert not store.revoke_device(999)

    def test_get_device_by_api_key(self, store):
        session = store.create_pairing_session()
        device = store.confirm_pairing(session["token"])
        found = store.get_device_by_api_key(device["api_key"])
        assert found is not None
        assert found["id"] == device["id"]

    def test_update_device_last_seen(self, store):
        session = store.create_pairing_session()
        device = store.confirm_pairing(session["token"])
        assert device.get("last_seen_at") is None
        store.update_device_last_seen(device["id"])
        devices = store.get_paired_devices()
        assert devices[0]["last_seen_at"] is not None

    def test_cleanup_expired_sessions(self, store):
        # Create a session with very short expiry
        session = store.create_pairing_session(expiry_minutes=0)
        # It should be expired immediately
        count = store.cleanup_expired_pairing_sessions()
        assert count >= 1

    def test_unique_api_keys(self, store):
        s1 = store.create_pairing_session()
        s2 = store.create_pairing_session()
        d1 = store.confirm_pairing(s1["token"])
        d2 = store.confirm_pairing(s2["token"])
        assert d1["api_key"] != d2["api_key"]
