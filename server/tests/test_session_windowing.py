"""Tests for session windowing logic and the /api/session-status endpoint."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import Config
from data.video_store import VideoStore
from invidious.client import InvidiousClient
from api import routes as api_routes
from utils import compute_session_state


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
def auth_headers():
    return {"Authorization": "Bearer test-key"}


def _now():
    return datetime.now(timezone.utc)


def _ts(dt: datetime) -> str:
    """Format datetime as SQLite-style UTC string."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ── Unit tests: compute_session_state ───────────────────────────────

class TestComputeSessionState:
    def _cfg(self, session_min=30, cooldown_min=15, max_sessions=None):
        return {
            "session_duration_minutes": session_min,
            "cooldown_duration_minutes": cooldown_min,
            "max_sessions_per_day": max_sessions,
        }

    def test_no_watch_time_returns_full_session(self):
        now = _now()
        state = compute_session_state(self._cfg(session_min=30), [], now)
        assert state["sessions_enabled"] is True
        assert state["in_cooldown"] is False
        assert state["sessions_exhausted"] is False
        assert state["current_session"] == 1
        assert state["session_time_remaining_seconds"] == 30 * 60
        assert state["cooldown_remaining_seconds"] == 0
        assert state["next_session_at"] is None

    def test_partial_session_shows_correct_remaining(self):
        now = _now()
        # 10 minutes watched in a 30-minute session
        t = now - timedelta(minutes=10)
        entries = [(600, _ts(t))]
        state = compute_session_state(self._cfg(session_min=30), entries, now)
        assert state["in_cooldown"] is False
        assert state["session_time_remaining_seconds"] == 20 * 60
        assert state["current_session"] == 1

    def test_session_complete_triggers_cooldown(self):
        now = _now()
        # 30 minutes watched → session complete, cooldown starts
        t = now - timedelta(minutes=5)  # session ended 5 min ago
        entries = [(30 * 60, _ts(t))]
        state = compute_session_state(self._cfg(session_min=30, cooldown_min=15), entries, now)
        assert state["in_cooldown"] is True
        assert state["sessions_exhausted"] is False
        assert state["current_session"] == 2
        # Cooldown should have ~10 minutes left (15 - 5 elapsed)
        assert 9 * 60 <= state["cooldown_remaining_seconds"] <= 10 * 60 + 5
        assert state["session_time_remaining_seconds"] == 0

    def test_cooldown_expired_by_now(self):
        now = _now()
        # Session ended 20 minutes ago, cooldown is 15 min → cooldown over
        t = now - timedelta(minutes=20)
        entries = [(30 * 60, _ts(t))]
        state = compute_session_state(self._cfg(session_min=30, cooldown_min=15), entries, now)
        assert state["in_cooldown"] is False
        assert state["current_session"] == 2
        assert state["session_time_remaining_seconds"] == 30 * 60
        assert state["cooldown_remaining_seconds"] == 0

    def test_second_session_in_progress(self):
        now = _now()
        # Session 1 complete (35 min ago), cooldown 15 min (expired 20 min ago)
        # Session 2: 10 min watched so far
        t1 = now - timedelta(minutes=35)
        t2 = now - timedelta(minutes=10)
        entries = [(30 * 60, _ts(t1)), (10 * 60, _ts(t2))]
        state = compute_session_state(self._cfg(session_min=30, cooldown_min=15), entries, now)
        assert state["in_cooldown"] is False
        assert state["current_session"] == 2
        assert state["session_time_remaining_seconds"] == 20 * 60

    def test_max_sessions_exhausted(self):
        now = _now()
        # 2 sessions of 30 min each, with 15 min cooldowns, max=2
        t1 = now - timedelta(minutes=120)
        t2 = now - timedelta(minutes=60)
        entries = [(30 * 60, _ts(t1)), (30 * 60, _ts(t2))]
        state = compute_session_state(
            self._cfg(session_min=30, cooldown_min=15, max_sessions=2),
            entries,
            now,
        )
        assert state["sessions_exhausted"] is True
        assert state["in_cooldown"] is False
        assert state["session_time_remaining_seconds"] == 0
        assert state["cooldown_remaining_seconds"] == 0

    def test_max_sessions_not_yet_exhausted(self):
        now = _now()
        # 1 session done, max=3, cooldown expired
        t1 = now - timedelta(minutes=60)
        entries = [(30 * 60, _ts(t1))]
        state = compute_session_state(
            self._cfg(session_min=30, cooldown_min=15, max_sessions=3),
            entries,
            now,
        )
        assert state["sessions_exhausted"] is False
        assert state["current_session"] == 2
        assert state["max_sessions"] == 3

    def test_heartbeats_during_cooldown_are_skipped(self):
        now = _now()
        # Session 1 ends at t1, cooldown 15 min
        # Rogue heartbeats at t1+5min (during cooldown) should not count
        t1 = now - timedelta(minutes=20)
        t_rogue = now - timedelta(minutes=14)  # during cooldown
        t2 = now - timedelta(minutes=3)   # after cooldown (ends at t1+15=now-5min)
        entries = [
            (30 * 60, _ts(t1)),    # completes session 1
            (5 * 60, _ts(t_rogue)),  # during cooldown → should be skipped
            (3 * 60, _ts(t2)),     # session 2, 3 min in
        ]
        state = compute_session_state(self._cfg(session_min=30, cooldown_min=15), entries, now)
        assert state["in_cooldown"] is False
        assert state["current_session"] == 2
        # 30min - 3min = 27min remaining in session 2 (rogue not counted)
        assert state["session_time_remaining_seconds"] == 27 * 60

    def test_multiple_small_heartbeats_accumulate(self):
        now = _now()
        # 60 heartbeats of 30 seconds each = 30 minutes → session complete
        t = now - timedelta(minutes=35)
        entries = [(30, _ts(t + timedelta(seconds=i * 30))) for i in range(60)]
        state = compute_session_state(self._cfg(session_min=30, cooldown_min=15), entries, now)
        # Last heartbeat at t + 29.5 min = now - 5.5 min
        # Cooldown: 15 min from that point → not yet expired (10 min remaining)
        assert state["in_cooldown"] is True
        assert state["current_session"] == 2

    def test_response_includes_all_fields(self):
        now = _now()
        cfg = self._cfg(session_min=45, cooldown_min=20, max_sessions=3)
        state = compute_session_state(cfg, [], now)
        assert state["sessions_enabled"] is True
        assert state["session_duration_minutes"] == 45
        assert state["cooldown_duration_minutes"] == 20
        assert state["max_sessions"] == 3
        assert state["current_session"] == 1
        assert state["in_cooldown"] is False
        assert state["sessions_exhausted"] is False
        assert state["session_time_remaining_seconds"] == 45 * 60
        assert state["cooldown_remaining_seconds"] == 0
        assert state["next_session_at"] is None

    def test_uncapped_sessions(self):
        now = _now()
        # max_sessions=None → sessions never exhausted
        cfg = self._cfg(session_min=30, cooldown_min=5, max_sessions=None)
        # Complete 5 sessions
        entries = []
        t = now - timedelta(minutes=300)
        for i in range(5):
            t_session = t + timedelta(minutes=i * 35)
            entries.append((30 * 60, _ts(t_session)))
        state = compute_session_state(cfg, entries, now)
        assert state["sessions_exhausted"] is False
        assert state["max_sessions"] is None


# ── VideoStore session config tests ─────────────────────────────────

class TestVideoStoreSessionConfig:
    def test_no_config_returns_none(self, store):
        child = store.add_child("Alex")
        assert store.get_session_config(child["id"]) is None

    def test_set_and_get_config(self, store):
        child = store.add_child("Alex")
        store.set_session_config(child["id"], 30, 15, 3)
        cfg = store.get_session_config(child["id"])
        assert cfg is not None
        assert cfg["session_duration_minutes"] == 30
        assert cfg["cooldown_duration_minutes"] == 15
        assert cfg["max_sessions_per_day"] == 3

    def test_set_config_without_max(self, store):
        child = store.add_child("Alex")
        store.set_session_config(child["id"], 60, 30)
        cfg = store.get_session_config(child["id"])
        assert cfg is not None
        assert cfg["max_sessions_per_day"] is None

    def test_clear_config(self, store):
        child = store.add_child("Alex")
        store.set_session_config(child["id"], 30, 15, 2)
        store.clear_session_config(child["id"])
        assert store.get_session_config(child["id"]) is None

    def test_upsert_overwrites(self, store):
        child = store.add_child("Alex")
        store.set_session_config(child["id"], 30, 15, 3)
        store.set_session_config(child["id"], 60, 30, None)
        cfg = store.get_session_config(child["id"])
        assert cfg["session_duration_minutes"] == 60
        assert cfg["cooldown_duration_minutes"] == 30
        assert cfg["max_sessions_per_day"] is None

    def test_get_watch_log_for_day(self, store):
        child = store.add_child("Alex")
        store.add_video("abcdefghijk", "Test", "Channel")
        store.record_watch_seconds("abcdefghijk", child["id"], 30)
        store.record_watch_seconds("abcdefghijk", child["id"], 30)
        from utils import get_today_str, get_day_utc_bounds
        today = get_today_str()
        bounds = get_day_utc_bounds(today)
        entries = store.get_watch_log_for_day(child["id"], bounds)
        assert len(entries) == 2
        assert all(isinstance(d, int) for d, _ in entries)
        assert all(isinstance(ts, str) for _, ts in entries)


# ── API endpoint tests ───────────────────────────────────────────────

class TestSessionStatusEndpoint:
    def test_child_not_found_returns_404(self, client, auth_headers):
        resp = client.get("/api/session-status?child_id=999", headers=auth_headers)
        assert resp.status_code == 404

    def test_no_session_config_returns_disabled(self, client, auth_headers, store):
        child = store.add_child("Alex")
        resp = client.get(
            f"/api/session-status?child_id={child['id']}", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions_enabled"] is False

    def test_session_configured_returns_full_state(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.set_session_config(child["id"], 30, 15, 3)
        resp = client.get(
            f"/api/session-status?child_id={child['id']}", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions_enabled"] is True
        assert data["current_session"] == 1
        assert data["session_duration_minutes"] == 30
        assert data["cooldown_duration_minutes"] == 15
        assert data["max_sessions"] == 3
        assert data["in_cooldown"] is False
        assert data["sessions_exhausted"] is False
        assert data["session_time_remaining_seconds"] == 30 * 60

    def test_no_watch_time_full_session_remaining(self, client, auth_headers, store):
        child = store.add_child("Alex")
        store.set_session_config(child["id"], 45, 20)
        resp = client.get(
            f"/api/session-status?child_id={child['id']}", headers=auth_headers
        )
        data = resp.json()
        assert data["session_time_remaining_seconds"] == 45 * 60

    def test_requires_auth(self, client):
        resp = client.get("/api/session-status?child_id=1")
        assert resp.status_code == 401


# ── Heartbeat integration: session affects remaining time ────────────

class TestHeartbeatSessionIntegration:
    def test_in_cooldown_returns_zero(self, client, auth_headers, store, cfg):
        child = store.add_child("Alex")
        # Set a daily limit
        store.set_child_setting(child["id"], "daily_limit_minutes", "120")
        # 30 min session, now in cooldown
        store.set_session_config(child["id"], 30, 30)

        # Record 30 min of watch time to complete session
        # Use a timestamp 5 minutes in the past to trigger cooldown
        from datetime import datetime, timedelta, timezone
        t = datetime.now(timezone.utc) - timedelta(minutes=5)
        conn = store.conn
        conn.execute(
            "INSERT INTO watch_log (video_id, child_id, duration, watched_at) VALUES (?, ?, ?, ?)",
            ("abcdefghijk", child["id"], 30 * 60, t.strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()

        store.add_video("abcdefghijk", "Test Video", "Test Channel")
        store.request_video(child["id"], "abcdefghijk")
        store.update_video_status(child["id"], "abcdefghijk", "approved")

        resp = client.post(
            "/api/watch-heartbeat",
            json={"video_id": "abcdefghijk", "child_id": child["id"], "seconds": 30},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["remaining"] == 0
