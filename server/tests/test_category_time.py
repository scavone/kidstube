"""Tests for category time limits: VideoStore methods and API endpoints."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from config import Config
from data.video_store import VideoStore
from invidious.client import InvidiousClient
from main import create_app
from api import routes as api_routes


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    s = VideoStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def cfg():
    return Config(
        app_name="TestApp",
        api_key="test-key",
        watch_limits=Config.__dataclass_fields__["watch_limits"].default_factory(),
    )


@pytest.fixture
def app(cfg, store):
    from fastapi import FastAPI
    a = FastAPI()
    a.state.api_key = cfg.api_key
    api_routes.setup(store, InvidiousClient(base_url="http://test:3000"), cfg)
    a.include_router(api_routes.router)
    a.include_router(api_routes.public_router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth():
    return {"Authorization": "Bearer test-key"}


# ── VideoStore: category limit CRUD ─────────────────────────────────

class TestCategoryLimitCRUD:
    def test_set_and_get_category_limit(self, store):
        child = store.add_child("Alex")
        store.set_category_limit(child["id"], "fun", 60)
        limits = store.get_category_limits(child["id"])
        assert limits == {"fun": 60}

    def test_multiple_categories(self, store):
        child = store.add_child("Alex")
        store.set_category_limit(child["id"], "fun", 60)
        store.set_category_limit(child["id"], "edu", 120)
        limits = store.get_category_limits(child["id"])
        assert limits == {"fun": 60, "edu": 120}

    def test_update_category_limit(self, store):
        child = store.add_child("Alex")
        store.set_category_limit(child["id"], "fun", 60)
        store.set_category_limit(child["id"], "fun", 90)
        limits = store.get_category_limits(child["id"])
        assert limits["fun"] == 90

    def test_clear_category_limit(self, store):
        child = store.add_child("Alex")
        store.set_category_limit(child["id"], "fun", 60)
        store.set_category_limit(child["id"], "edu", 120)
        store.clear_category_limit(child["id"], "fun")
        limits = store.get_category_limits(child["id"])
        assert "fun" not in limits
        assert limits["edu"] == 120

    def test_clear_nonexistent_limit_is_noop(self, store):
        child = store.add_child("Alex")
        # Should not raise
        store.clear_category_limit(child["id"], "nonexistent")
        assert store.get_category_limits(child["id"]) == {}

    def test_no_limits_returns_empty_dict(self, store):
        child = store.add_child("Alex")
        assert store.get_category_limits(child["id"]) == {}


# ── VideoStore: category bonus ──────────────────────────────────────

class TestCategoryBonus:
    def test_get_bonus_default_zero(self, store):
        child = store.add_child("Alex")
        assert store.get_category_bonus(child["id"], "fun", "2026-03-24") == 0

    def test_add_category_bonus(self, store):
        child = store.add_child("Alex")
        store.add_category_bonus(child["id"], "fun", 15, "2026-03-24")
        assert store.get_category_bonus(child["id"], "fun", "2026-03-24") == 15

    def test_add_category_bonus_accumulates(self, store):
        child = store.add_child("Alex")
        store.add_category_bonus(child["id"], "fun", 10, "2026-03-24")
        store.add_category_bonus(child["id"], "fun", 5, "2026-03-24")
        assert store.get_category_bonus(child["id"], "fun", "2026-03-24") == 15

    def test_bonus_is_per_date(self, store):
        child = store.add_child("Alex")
        store.add_category_bonus(child["id"], "fun", 10, "2026-03-24")
        assert store.get_category_bonus(child["id"], "fun", "2026-03-25") == 0

    def test_bonus_is_per_category(self, store):
        child = store.add_child("Alex")
        store.add_category_bonus(child["id"], "fun", 10, "2026-03-24")
        assert store.get_category_bonus(child["id"], "edu", "2026-03-24") == 0


# ── VideoStore: category watch minutes ──────────────────────────────

class TestCategoryWatchMinutes:
    def _insert_watch(self, store, video_id, child_id, seconds, category):
        """Direct DB insert with explicit category for testing."""
        with store._lock:
            store.conn.execute(
                "INSERT INTO watch_log (video_id, child_id, duration, category, watched_at)"
                " VALUES (?, ?, ?, ?, datetime('now'))",
                (video_id, child_id, seconds, category),
            )
            store.conn.commit()

    def test_no_watches_returns_zero(self, store):
        child = store.add_child("Alex")
        result = store.get_daily_category_watch_minutes(
            child["id"], "2026-03-24", "fun"
        )
        assert result == 0.0

    def test_counts_matching_category(self, store):
        child = store.add_child("Alex")
        self._insert_watch(store, "vid1", child["id"], 600, "fun")  # 10 min
        self._insert_watch(store, "vid2", child["id"], 300, "edu")  # 5 min
        result = store.get_daily_category_watch_minutes(
            child["id"], "2026-03-24", "fun",
            utc_bounds=("2026-03-24T00:00:00", "2026-03-25T00:00:00"),
        )
        assert result == pytest.approx(10.0, abs=0.1)

    def test_excludes_other_categories(self, store):
        child = store.add_child("Alex")
        self._insert_watch(store, "vid1", child["id"], 600, "edu")
        result = store.get_daily_category_watch_minutes(
            child["id"], "2026-03-24", "fun",
            utc_bounds=("2026-03-24T00:00:00", "2026-03-25T00:00:00"),
        )
        assert result == 0.0


# ── VideoStore: record_watch_seconds writes category ────────────────

class TestRecordWatchSeconds:
    def test_defaults_to_fun_when_no_video_record(self, store):
        child = store.add_child("Alex")
        store.record_watch_seconds("unknownvid11", child["id"], 60)
        with store._lock:
            row = store.conn.execute(
                "SELECT category FROM watch_log WHERE video_id = ?",
                ("unknownvid11",),
            ).fetchone()
        assert row is not None
        assert row[0] == "fun"

    def test_uses_video_category(self, store):
        child = store.add_child("Alex")
        store.add_video(
            "eduvideo1234", "Edu Video", "Edu Channel",
            category="edu",
        )
        store.record_watch_seconds("eduvideo1234", child["id"], 60)
        with store._lock:
            row = store.conn.execute(
                "SELECT category FROM watch_log WHERE video_id = ?",
                ("eduvideo1234",),
            ).fetchone()
        assert row[0] == "edu"

    def test_falls_back_to_channel_category(self, store):
        child = store.add_child("Alex")
        # Video has no category; channel has one
        store.add_video("musicvid1234", "Music Video", "Music Channel")
        store.add_channel(child["id"], "Music Channel", "allowed", category="music")
        store.record_watch_seconds("musicvid1234", child["id"], 60)
        with store._lock:
            row = store.conn.execute(
                "SELECT category FROM watch_log WHERE video_id = ?",
                ("musicvid1234",),
            ).fetchone()
        assert row[0] == "music"


# ── VideoStore: get_video_effective_category ─────────────────────────

class TestGetVideoEffectiveCategory:
    def test_returns_fun_for_unknown_video(self, store):
        child = store.add_child("Alex")
        assert store.get_video_effective_category("unknownvid11", child["id"]) == "fun"

    def test_returns_video_category(self, store):
        child = store.add_child("Alex")
        store.add_video("eduvideo1234", "Edu", "Ch", category="edu")
        assert store.get_video_effective_category("eduvideo1234", child["id"]) == "edu"

    def test_prefers_video_category_over_channel(self, store):
        child = store.add_child("Alex")
        store.add_video("vid12345678a", "Vid", "Music Channel", category="edu")
        store.add_channel(child["id"], "Music Channel", "allowed", category="music")
        assert store.get_video_effective_category("vid12345678a", child["id"]) == "edu"

    def test_falls_back_to_channel_category(self, store):
        child = store.add_child("Alex")
        store.add_video("vid12345678b", "Vid", "Music Channel")
        store.add_channel(child["id"], "Music Channel", "allowed", category="music")
        assert store.get_video_effective_category("vid12345678b", child["id"]) == "music"


# ── API: GET /api/category-time-status ──────────────────────────────

class TestCategoryTimeStatusEndpoint:
    def test_child_not_found_returns_404(self, client, auth):
        resp = client.get("/api/category-time-status?child_id=999", headers=auth)
        assert resp.status_code == 404

    def test_no_limits_returns_empty(self, client, auth, store):
        child = store.add_child("Alex")
        resp = client.get(f"/api/category-time-status?child_id={child['id']}", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert data["categories"] == {}
        assert data["uncapped_categories"] == []

    def test_returns_category_with_limits(self, client, auth, store):
        child = store.add_child("Alex")
        store.set_category_limit(child["id"], "fun", 60)
        resp = client.get(f"/api/category-time-status?child_id={child['id']}", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "fun" in data["categories"]
        entry = data["categories"]["fun"]
        assert entry["limit_minutes"] == 60
        assert entry["used_minutes"] == 0.0
        assert entry["remaining_minutes"] == 60.0
        assert entry["remaining_seconds"] == 3600
        assert entry["bonus_minutes"] == 0
        assert entry["exhausted"] is False

    def test_exhausted_flag_when_used_exceeds_limit(self, client, auth, store):
        child = store.add_child("Alex")
        store.set_category_limit(child["id"], "fun", 1)  # 1 min limit
        # Insert 120 seconds (2 min) of fun watch time
        with store._lock:
            store.conn.execute(
                "INSERT INTO watch_log (video_id, child_id, duration, category, watched_at)"
                " VALUES ('vid12345678a', ?, 120, 'fun', datetime('now'))",
                (child["id"],),
            )
            store.conn.commit()
        resp = client.get(f"/api/category-time-status?child_id={child['id']}", headers=auth)
        data = resp.json()
        assert data["categories"]["fun"]["exhausted"] is True
        assert data["categories"]["fun"]["remaining_minutes"] == 0.0

    def test_bonus_adds_to_remaining(self, client, auth, store, cfg):
        from utils import get_today_str
        child = store.add_child("Alex")
        store.set_category_limit(child["id"], "edu", 30)
        today = get_today_str(cfg.watch_limits.timezone)
        store.add_category_bonus(child["id"], "edu", 15, today)
        resp = client.get(f"/api/category-time-status?child_id={child['id']}", headers=auth)
        data = resp.json()
        entry = data["categories"]["edu"]
        assert entry["limit_minutes"] == 30
        assert entry["bonus_minutes"] == 15
        assert entry["remaining_minutes"] == 45.0

    def test_uncapped_categories_from_watch_log(self, client, auth, store):
        child = store.add_child("Alex")
        # No category limits, but has some watch time
        with store._lock:
            store.conn.execute(
                "INSERT INTO watch_log (video_id, child_id, duration, category, watched_at)"
                " VALUES ('vid12345678a', ?, 60, 'music', datetime('now'))",
                (child["id"],),
            )
            store.conn.commit()
        resp = client.get(f"/api/category-time-status?child_id={child['id']}", headers=auth)
        data = resp.json()
        assert "music" in data["uncapped_categories"]

    def test_limited_category_not_in_uncapped(self, client, auth, store):
        child = store.add_child("Alex")
        store.set_category_limit(child["id"], "fun", 60)
        with store._lock:
            store.conn.execute(
                "INSERT INTO watch_log (video_id, child_id, duration, category, watched_at)"
                " VALUES ('vid12345678a', ?, 60, 'fun', datetime('now'))",
                (child["id"],),
            )
            store.conn.commit()
        resp = client.get(f"/api/category-time-status?child_id={child['id']}", headers=auth)
        data = resp.json()
        assert "fun" not in data["uncapped_categories"]
        assert "fun" in data["categories"]


# ── API: GET /api/time-status includes category_status ──────────────

class TestTimeStatusCategoryField:
    def test_no_category_limits_omits_category_status(self, client, auth, store):
        child = store.add_child("Alex")
        resp = client.get(f"/api/time-status?child_id={child['id']}", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert data["category_status"] is None

    def test_with_category_limits_includes_category_status(self, client, auth, store):
        child = store.add_child("Alex")
        store.set_category_limit(child["id"], "fun", 60)
        resp = client.get(f"/api/time-status?child_id={child['id']}", headers=auth)
        data = resp.json()
        assert data["category_status"] is not None
        assert data["category_status"]["has_limits"] is True
        assert "fun" in data["category_status"]["categories"]


# ── Backward compatibility ────────────────────────────────────────────

class TestBackwardCompatibility:
    def test_existing_time_status_fields_unchanged(self, client, auth, store):
        child = store.add_child("Alex")
        resp = client.get(f"/api/time-status?child_id={child['id']}", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "limit_min" in data
        assert "used_min" in data
        assert "remaining_min" in data
        assert "remaining_sec" in data
        assert "exceeded" in data

    def test_watch_log_without_category_column_still_works(self, tmp_path):
        """Simulate an old DB without the category column — migration should add it."""
        import sqlite3
        old_db = str(tmp_path / "old.db")
        # Create old-style watch_log without category column
        conn = sqlite3.connect(old_db)
        conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE children (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE COLLATE NOCASE, avatar TEXT DEFAULT '👦', created_at TEXT NOT NULL DEFAULT (datetime('now')));
            CREATE TABLE watch_log (id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL, child_id INTEGER NOT NULL, duration INTEGER NOT NULL, watched_at TEXT NOT NULL DEFAULT (datetime('now')));
            INSERT INTO children (name) VALUES ('Alex');
            INSERT INTO watch_log (video_id, child_id, duration) VALUES ('vid1', 1, 60);
        """)
        conn.commit()
        conn.close()

        # Opening VideoStore should migrate and add the column
        s = VideoStore(old_db)
        # After migration, we can query the category column
        with s._lock:
            row = s.conn.execute("SELECT category FROM watch_log WHERE child_id = 1").fetchone()
        assert row is not None
        assert row[0] == "fun"  # DEFAULT 'fun' applied
        s.close()
