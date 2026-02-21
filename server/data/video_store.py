"""SQLite-backed data layer with multi-child profile support.

Extends BrainRotGuard's VideoStore patterns with:
- children table (profiles)
- child_settings (per-child daily limits, schedules, category budgets)
- child_video_access (per-child approval status)
- watch_log keyed by child_id
"""

import sqlite3
import threading
from pathlib import Path
from typing import Optional


class VideoStore:
    """SQLite database for video approval, child profiles, and watch tracking."""

    def __init__(self, db_path: str = "db/videos.db"):
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS children (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                avatar TEXT DEFAULT '👦',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS child_settings (
                child_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (child_id, key),
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                channel_id TEXT,
                thumbnail_url TEXT,
                duration INTEGER,
                category TEXT,
                requested_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS child_video_access (
                child_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                requested_at TEXT NOT NULL DEFAULT (datetime('now')),
                decided_at TEXT,
                PRIMARY KEY (child_id, video_id),
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS watch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                child_id INTEGER NOT NULL,
                duration INTEGER NOT NULL,
                watched_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_watch_log_date
                ON watch_log(watched_at);
            CREATE INDEX IF NOT EXISTS idx_watch_log_child
                ON watch_log(child_id, watched_at);
            CREATE INDEX IF NOT EXISTS idx_child_video_access_status
                ON child_video_access(status);

            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                channel_id TEXT,
                handle TEXT,
                status TEXT NOT NULL DEFAULT 'allowed',
                category TEXT,
                added_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS word_filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL UNIQUE COLLATE NOCASE,
                added_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS search_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                child_id INTEGER,
                result_count INTEGER NOT NULL DEFAULT 0,
                searched_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_search_log_date
                ON search_log(searched_at);
        """)
        self.conn.commit()

    # ── Child Profiles ──────────────────────────────────────────────

    def add_child(self, name: str, avatar: str = "👦") -> Optional[dict]:
        """Create a child profile. Returns the created child or None on conflict."""
        with self._lock:
            try:
                cursor = self.conn.execute(
                    "INSERT INTO children (name, avatar) VALUES (?, ?)",
                    (name, avatar),
                )
                self.conn.commit()
                child_id = cursor.lastrowid
                row = self.conn.execute(
                    "SELECT * FROM children WHERE id = ?", (child_id,)
                ).fetchone()
                return dict(row) if row else None
            except sqlite3.IntegrityError:
                return None

    def get_children(self) -> list[dict]:
        """List all child profiles."""
        with self._lock:
            cursor = self.conn.execute(
                "SELECT * FROM children ORDER BY name"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_child(self, child_id: int) -> Optional[dict]:
        """Get a single child by ID."""
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM children WHERE id = ?", (child_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_child_by_name(self, name: str) -> Optional[dict]:
        """Get a child by name (case-insensitive)."""
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM children WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            return dict(row) if row else None

    def remove_child(self, child_id: int) -> bool:
        """Delete a child profile and all related data (CASCADE)."""
        with self._lock:
            cursor = self.conn.execute(
                "DELETE FROM children WHERE id = ?", (child_id,)
            )
            self.conn.commit()
            return cursor.rowcount > 0

    # ── Child Settings ──────────────────────────────────────────────

    def get_child_setting(self, child_id: int, key: str, default: str = "") -> str:
        """Read a per-child setting value."""
        with self._lock:
            row = self.conn.execute(
                "SELECT value FROM child_settings WHERE child_id = ? AND key = ?",
                (child_id, key),
            ).fetchone()
            return row[0] if row else default

    def set_child_setting(self, child_id: int, key: str, value: str) -> None:
        """Write a per-child setting (upsert)."""
        with self._lock:
            self.conn.execute(
                """INSERT INTO child_settings (child_id, key, value)
                   VALUES (?, ?, ?)
                   ON CONFLICT(child_id, key)
                   DO UPDATE SET value = ?, updated_at = datetime('now')""",
                (child_id, key, value, value),
            )
            self.conn.commit()

    def get_child_settings(self, child_id: int) -> dict[str, str]:
        """Get all settings for a child as a dict."""
        with self._lock:
            cursor = self.conn.execute(
                "SELECT key, value FROM child_settings WHERE child_id = ?",
                (child_id,),
            )
            return {row[0]: row[1] for row in cursor.fetchall()}

    # ── Videos ──────────────────────────────────────────────────────

    def add_video(
        self,
        video_id: str,
        title: str,
        channel_name: str,
        channel_id: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        duration: Optional[int] = None,
        category: Optional[str] = None,
    ) -> dict:
        """Add a video to the catalog. If it already exists, return existing."""
        with self._lock:
            self.conn.execute(
                """INSERT OR IGNORE INTO videos
                   (video_id, title, channel_name, channel_id, thumbnail_url, duration, category)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (video_id, title, channel_name, channel_id, thumbnail_url, duration, category),
            )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT * FROM videos WHERE video_id = ?", (video_id,)
            ).fetchone()
            return dict(row) if row else {}

    def get_video(self, video_id: str) -> Optional[dict]:
        """Get a video by its YouTube ID."""
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM videos WHERE video_id = ?", (video_id,)
            ).fetchone()
            return dict(row) if row else None

    # ── Per-Child Video Access ──────────────────────────────────────

    def request_video(self, child_id: int, video_id: str) -> str:
        """Request access to a video for a child.

        Returns the status: 'pending', 'approved', 'denied', or 'auto_approved'.
        """
        with self._lock:
            # Check if access already exists
            row = self.conn.execute(
                "SELECT status FROM child_video_access WHERE child_id = ? AND video_id = ?",
                (child_id, video_id),
            ).fetchone()
            if row:
                return row[0]

            # Check if channel is blocked
            video = self.conn.execute(
                "SELECT channel_name FROM videos WHERE video_id = ?", (video_id,)
            ).fetchone()
            if video:
                blocked = self.conn.execute(
                    "SELECT 1 FROM channels WHERE channel_name = ? COLLATE NOCASE AND status = 'blocked'",
                    (video["channel_name"],),
                ).fetchone()
                if blocked:
                    self.conn.execute(
                        """INSERT INTO child_video_access (child_id, video_id, status, decided_at)
                           VALUES (?, ?, 'denied', datetime('now'))""",
                        (child_id, video_id),
                    )
                    self.conn.commit()
                    return "denied"

                # Check if channel is allowed -> auto-approve
                allowed = self.conn.execute(
                    "SELECT 1 FROM channels WHERE channel_name = ? COLLATE NOCASE AND status = 'allowed'",
                    (video["channel_name"],),
                ).fetchone()
                if allowed:
                    self.conn.execute(
                        """INSERT INTO child_video_access (child_id, video_id, status, decided_at)
                           VALUES (?, ?, 'approved', datetime('now'))""",
                        (child_id, video_id),
                    )
                    self.conn.commit()
                    return "auto_approved"

            # No list match -> pending
            self.conn.execute(
                "INSERT INTO child_video_access (child_id, video_id, status) VALUES (?, ?, 'pending')",
                (child_id, video_id),
            )
            self.conn.commit()
            return "pending"

    def get_video_status(self, child_id: int, video_id: str) -> Optional[str]:
        """Get a child's access status for a video."""
        with self._lock:
            row = self.conn.execute(
                "SELECT status FROM child_video_access WHERE child_id = ? AND video_id = ?",
                (child_id, video_id),
            ).fetchone()
            return row[0] if row else None

    def update_video_status(self, child_id: int, video_id: str, status: str) -> bool:
        """Update a child's access status for a video. Returns True if updated."""
        with self._lock:
            cursor = self.conn.execute(
                """UPDATE child_video_access
                   SET status = ?, decided_at = datetime('now')
                   WHERE child_id = ? AND video_id = ?""",
                (status, child_id, video_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0

    def get_pending_requests(self, child_id: Optional[int] = None) -> list[dict]:
        """Get pending video requests, optionally filtered by child."""
        with self._lock:
            if child_id is not None:
                cursor = self.conn.execute(
                    """SELECT cva.*, v.title, v.channel_name, v.thumbnail_url, v.duration,
                              c.name as child_name
                       FROM child_video_access cva
                       JOIN videos v ON cva.video_id = v.video_id
                       JOIN children c ON cva.child_id = c.id
                       WHERE cva.status = 'pending' AND cva.child_id = ?
                       ORDER BY cva.requested_at DESC""",
                    (child_id,),
                )
            else:
                cursor = self.conn.execute(
                    """SELECT cva.*, v.title, v.channel_name, v.thumbnail_url, v.duration,
                              c.name as child_name
                       FROM child_video_access cva
                       JOIN videos v ON cva.video_id = v.video_id
                       JOIN children c ON cva.child_id = c.id
                       WHERE cva.status = 'pending'
                       ORDER BY cva.requested_at DESC"""
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_approved_videos(self, child_id: int, category: Optional[str] = None,
                            channel: Optional[str] = None,
                            offset: int = 0, limit: int = 24) -> tuple[list[dict], int]:
        """Get paginated approved videos for a child.

        Returns (videos, total_count).
        """
        with self._lock:
            where_parts = ["cva.status = 'approved'", "cva.child_id = ?"]
            params: list = [child_id]

            if category:
                where_parts.append("COALESCE(v.category, ch.category, 'fun') = ?")
                params.append(category)
            if channel:
                where_parts.append("v.channel_name = ? COLLATE NOCASE")
                params.append(channel)

            where_clause = " AND ".join(where_parts)

            count_row = self.conn.execute(
                f"""SELECT COUNT(*) FROM child_video_access cva
                    JOIN videos v ON cva.video_id = v.video_id
                    LEFT JOIN channels ch ON v.channel_name = ch.channel_name COLLATE NOCASE
                    WHERE {where_clause}""",
                params,
            ).fetchone()
            total = count_row[0] if count_row else 0

            cursor = self.conn.execute(
                f"""SELECT v.*, COALESCE(v.category, ch.category, 'fun') as effective_category,
                           cva.decided_at as access_decided_at
                    FROM child_video_access cva
                    JOIN videos v ON cva.video_id = v.video_id
                    LEFT JOIN channels ch ON v.channel_name = ch.channel_name COLLATE NOCASE
                    WHERE {where_clause}
                    ORDER BY cva.decided_at DESC
                    LIMIT ? OFFSET ?""",
                params + [limit, offset],
            )
            return [dict(row) for row in cursor.fetchall()], total

    # ── Watch Time Tracking ─────────────────────────────────────────

    def record_watch_seconds(self, video_id: str, child_id: int, seconds: int) -> None:
        """Log playback seconds from a heartbeat."""
        with self._lock:
            self.conn.execute(
                "INSERT INTO watch_log (video_id, child_id, duration) VALUES (?, ?, ?)",
                (video_id, child_id, seconds),
            )
            self.conn.commit()

    def get_daily_watch_minutes(
        self, child_id: int, date_str: str, utc_bounds: Optional[tuple[str, str]] = None
    ) -> float:
        """Sum watch time for a child on a date. Returns minutes."""
        start, end = utc_bounds if utc_bounds else (date_str, date_str)
        end_clause = "?" if utc_bounds else "date(?, '+1 day')"
        with self._lock:
            row = self.conn.execute(
                f"""SELECT COALESCE(SUM(duration), 0) FROM watch_log
                    WHERE child_id = ? AND watched_at >= ? AND watched_at < {end_clause}""",
                (child_id, start, end),
            ).fetchone()
            return row[0] / 60.0 if row else 0.0

    def get_daily_watch_breakdown(
        self, child_id: int, date_str: str, utc_bounds: Optional[tuple[str, str]] = None
    ) -> list[dict]:
        """Per-video watch time for a child on a date."""
        start, end = utc_bounds if utc_bounds else (date_str, date_str)
        end_clause = "?" if utc_bounds else "date(?, '+1 day')"
        with self._lock:
            cursor = self.conn.execute(
                f"""SELECT w.video_id, COALESCE(SUM(w.duration), 0) as total_sec,
                           v.title, v.channel_name, v.thumbnail_url, v.duration as video_duration
                    FROM watch_log w
                    LEFT JOIN videos v ON w.video_id = v.video_id
                    WHERE w.child_id = ? AND w.watched_at >= ? AND w.watched_at < {end_clause}
                    GROUP BY w.video_id
                    ORDER BY total_sec DESC""",
                (child_id, start, end),
            )
            return [
                {
                    "video_id": row[0],
                    "minutes": round(row[1] / 60.0, 1),
                    "title": row[2] or row[0],
                    "channel_name": row[3] or "Unknown",
                    "thumbnail_url": row[4] or "",
                    "video_duration": row[5],
                }
                for row in cursor.fetchall()
            ]

    # ── Channel Allow/Block Lists (Global) ──────────────────────────

    def add_channel(
        self, name: str, status: str,
        channel_id: Optional[str] = None,
        handle: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        """Add or update a channel in the allow/block list."""
        with self._lock:
            self.conn.execute(
                """INSERT INTO channels (channel_name, status, channel_id, handle, category)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(channel_name) DO UPDATE SET
                       status = ?,
                       channel_id = COALESCE(?, channel_id),
                       handle = COALESCE(?, handle),
                       category = COALESCE(?, category),
                       added_at = datetime('now')""",
                (name, status, channel_id, handle, category, status, channel_id, handle, category),
            )
            self.conn.commit()
            return True

    def remove_channel(self, name_or_handle: str) -> bool:
        """Remove a channel by name or @handle."""
        with self._lock:
            cursor = self.conn.execute(
                "DELETE FROM channels WHERE channel_name = ? COLLATE NOCASE OR handle = ? COLLATE NOCASE",
                (name_or_handle, name_or_handle),
            )
            self.conn.commit()
            return cursor.rowcount > 0

    def get_channels(self, status: Optional[str] = None) -> list[dict]:
        """List channels, optionally filtered by status."""
        with self._lock:
            if status:
                cursor = self.conn.execute(
                    "SELECT * FROM channels WHERE status = ? ORDER BY channel_name",
                    (status,),
                )
            else:
                cursor = self.conn.execute(
                    "SELECT * FROM channels ORDER BY channel_name"
                )
            return [dict(row) for row in cursor.fetchall()]

    def is_channel_allowed(self, name: str) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT 1 FROM channels WHERE channel_name = ? COLLATE NOCASE AND status = 'allowed'",
                (name,),
            ).fetchone()
            return row is not None

    def is_channel_blocked(self, name: str) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT 1 FROM channels WHERE channel_name = ? COLLATE NOCASE AND status = 'blocked'",
                (name,),
            ).fetchone()
            return row is not None

    def get_blocked_channels_set(self) -> set[str]:
        with self._lock:
            cursor = self.conn.execute(
                "SELECT channel_name FROM channels WHERE status = 'blocked'"
            )
            return {row[0].lower() for row in cursor.fetchall()}

    # ── Word Filters ────────────────────────────────────────────────

    def add_word_filter(self, word: str) -> bool:
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO word_filters (word) VALUES (?)", (word.lower(),)
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_word_filter(self, word: str) -> bool:
        with self._lock:
            cursor = self.conn.execute(
                "DELETE FROM word_filters WHERE word = ? COLLATE NOCASE", (word,)
            )
            self.conn.commit()
            return cursor.rowcount > 0

    def get_word_filters(self) -> list[str]:
        with self._lock:
            cursor = self.conn.execute(
                "SELECT word FROM word_filters ORDER BY word"
            )
            return [row[0] for row in cursor.fetchall()]

    def get_word_filters_set(self) -> set[str]:
        with self._lock:
            cursor = self.conn.execute("SELECT word FROM word_filters")
            return {row[0].lower() for row in cursor.fetchall()}

    # ── Global Settings ─────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self.conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT INTO settings (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = datetime('now')""",
                (key, value, value),
            )
            self.conn.commit()

    # ── Search Logging ──────────────────────────────────────────────

    def record_search(self, query: str, child_id: int, result_count: int) -> None:
        query = query[:200]
        with self._lock:
            self.conn.execute(
                "INSERT INTO search_log (query, child_id, result_count) VALUES (?, ?, ?)",
                (query, child_id, result_count),
            )
            self.conn.commit()

    # ── Stats ───────────────────────────────────────────────────────

    def get_stats(self, child_id: Optional[int] = None) -> dict:
        """Get aggregate statistics, optionally per-child."""
        with self._lock:
            if child_id is not None:
                row = self.conn.execute(
                    """SELECT
                        COUNT(*) as total,
                        COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) as pending,
                        COALESCE(SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END), 0) as approved,
                        COALESCE(SUM(CASE WHEN status = 'denied' THEN 1 ELSE 0 END), 0) as denied
                       FROM child_video_access WHERE child_id = ?""",
                    (child_id,),
                ).fetchone()
            else:
                row = self.conn.execute(
                    """SELECT
                        COUNT(*) as total,
                        COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) as pending,
                        COALESCE(SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END), 0) as approved,
                        COALESCE(SUM(CASE WHEN status = 'denied' THEN 1 ELSE 0 END), 0) as denied
                       FROM child_video_access"""
                ).fetchone()
            return dict(row) if row else {"total": 0, "pending": 0, "approved": 0, "denied": 0}

    def close(self) -> None:
        self.conn.close()
