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
                published_at INTEGER,
                requested_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS child_video_access (
                child_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                requested_at TEXT NOT NULL DEFAULT (datetime('now')),
                decided_at TEXT,
                watch_position INTEGER DEFAULT 0,
                watch_duration INTEGER DEFAULT 0,
                last_watched_at TEXT,
                watch_status TEXT,
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
                added_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_refreshed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS child_channels (
                child_id INTEGER NOT NULL,
                channel_name TEXT NOT NULL COLLATE NOCASE,
                channel_id TEXT,
                handle TEXT,
                status TEXT NOT NULL DEFAULT 'allowed',
                category TEXT,
                added_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_refreshed_at TEXT,
                PRIMARY KEY (child_id, channel_name),
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS channel_requests (
                child_id INTEGER NOT NULL,
                channel_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                requested_at TEXT NOT NULL DEFAULT (datetime('now')),
                decided_at TEXT,
                PRIMARY KEY (child_id, channel_id),
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
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
        self._migrate()

    def _migrate(self) -> None:
        """Apply schema migrations for existing databases."""
        cursor = self.conn.execute("PRAGMA table_info(channels)")
        columns = {row[1] for row in cursor.fetchall()}
        if "last_refreshed_at" not in columns:
            self.conn.execute(
                "ALTER TABLE channels ADD COLUMN last_refreshed_at TEXT"
            )
            self.conn.commit()

        # Add published_at column to videos table if missing
        cursor = self.conn.execute("PRAGMA table_info(videos)")
        video_columns = {row[1] for row in cursor.fetchall()}
        if "published_at" not in video_columns:
            self.conn.execute(
                "ALTER TABLE videos ADD COLUMN published_at INTEGER"
            )
            self.conn.commit()

        # Add description column to videos table if missing
        if "description" not in video_columns:
            self.conn.execute(
                "ALTER TABLE videos ADD COLUMN description TEXT"
            )
            self.conn.commit()

        # Add watch position tracking columns to child_video_access if missing
        cursor = self.conn.execute("PRAGMA table_info(child_video_access)")
        cva_columns = {row[1] for row in cursor.fetchall()}
        if "watch_position" not in cva_columns:
            self.conn.execute(
                "ALTER TABLE child_video_access ADD COLUMN watch_position INTEGER DEFAULT 0"
            )
            self.conn.execute(
                "ALTER TABLE child_video_access ADD COLUMN watch_duration INTEGER DEFAULT 0"
            )
            self.conn.execute(
                "ALTER TABLE child_video_access ADD COLUMN last_watched_at TEXT"
            )
            self.conn.commit()

        if "watch_status" not in cva_columns:
            self.conn.execute(
                "ALTER TABLE child_video_access ADD COLUMN watch_status TEXT"
            )
            # Backfill from existing position data
            self.conn.execute("""
                UPDATE child_video_access SET watch_status = 'in_progress'
                WHERE watch_status IS NULL AND watch_position > 0
                  AND watch_duration > 0 AND watch_position < watch_duration - 30
            """)
            self.conn.execute("""
                UPDATE child_video_access SET watch_status = 'watched'
                WHERE watch_status IS NULL AND watch_position > 0
                  AND watch_duration > 0 AND watch_position >= watch_duration - 30
            """)
            self.conn.commit()

        # Migrate global channels -> per-child channels for existing databases.
        # Copy any global channel entries that don't yet exist in child_channels
        # for each child, then leave the global table intact (unused going forward).
        tables = {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "child_channels" in tables:
            children = self.conn.execute("SELECT id FROM children").fetchall()
            global_channels = self.conn.execute("SELECT * FROM channels").fetchall()
            if children and global_channels:
                for child_row in children:
                    cid = child_row[0]
                    for ch in global_channels:
                        self.conn.execute(
                            """INSERT OR IGNORE INTO child_channels
                               (child_id, channel_name, channel_id, handle, status,
                                category, added_at, last_refreshed_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (cid, ch["channel_name"], ch["channel_id"],
                             ch["handle"], ch["status"], ch["category"],
                             ch["added_at"], ch["last_refreshed_at"]),
                        )
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

    def update_child(self, child_id: int, name: Optional[str] = None,
                     avatar: Optional[str] = None) -> Optional[dict]:
        """Update a child's name and/or avatar. Returns updated child or None."""
        with self._lock:
            child = self.conn.execute(
                "SELECT * FROM children WHERE id = ?", (child_id,)
            ).fetchone()
            if not child:
                return None

            new_name = name if name is not None else child["name"]
            new_avatar = avatar if avatar is not None else child["avatar"]

            try:
                self.conn.execute(
                    "UPDATE children SET name = ?, avatar = ? WHERE id = ?",
                    (new_name, new_avatar, child_id),
                )
                self.conn.commit()
            except sqlite3.IntegrityError:
                return None  # Name conflict

            row = self.conn.execute(
                "SELECT * FROM children WHERE id = ?", (child_id,)
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

    def get_avatar_dir(self) -> Path:
        """Return the avatar storage directory, creating it if needed."""
        db_dir = Path(self.conn.execute("PRAGMA database_list").fetchone()[2]).parent
        avatar_dir = db_dir / "avatars"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        return avatar_dir

    def save_avatar(self, child_id: int, photo_bytes: bytes) -> bool:
        """Save avatar photo to disk. Returns True on success."""
        child = self.get_child(child_id)
        if not child:
            return False
        avatar_path = self.get_avatar_dir() / f"{child_id}.jpg"
        avatar_path.write_bytes(photo_bytes)
        # Mark avatar field as "photo" to indicate file-based avatar
        with self._lock:
            self.conn.execute(
                "UPDATE children SET avatar = ? WHERE id = ?",
                ("photo", child_id),
            )
            self.conn.commit()
        return True

    def get_avatar_path(self, child_id: int) -> Optional[Path]:
        """Return the path to a child's avatar photo, or None if not found."""
        avatar_path = self.get_avatar_dir() / f"{child_id}.jpg"
        return avatar_path if avatar_path.exists() else None

    def delete_avatar(self, child_id: int) -> None:
        """Remove a child's avatar photo from disk."""
        avatar_path = self.get_avatar_dir() / f"{child_id}.jpg"
        if avatar_path.exists():
            avatar_path.unlink()

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
        published_at: Optional[int] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Add a video to the catalog. If it already exists, return existing."""
        with self._lock:
            self.conn.execute(
                """INSERT OR IGNORE INTO videos
                   (video_id, title, channel_name, channel_id, thumbnail_url, duration, category, published_at, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (video_id, title, channel_name, channel_id, thumbnail_url, duration, category, published_at, description),
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

    def bulk_import_channel_videos(
        self,
        videos: list[dict],
        category: str,
        child_ids: list[int],
    ) -> int:
        """Bulk-insert videos and auto-approve them for all specified children.

        Used when a channel is allowed — imports existing channel videos
        and grants access to all children.  Uses INSERT OR IGNORE so
        existing videos and existing access decisions are preserved.

        Returns the number of new videos inserted.
        """
        if not videos or not child_ids:
            return 0

        inserted = 0
        with self._lock:
            for v in videos:
                vid = v.get("video_id")
                if not vid:
                    continue

                cursor = self.conn.execute(
                    """INSERT OR IGNORE INTO videos
                       (video_id, title, channel_name, channel_id,
                        thumbnail_url, duration, category, published_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        vid,
                        v.get("title", ""),
                        v.get("channel_name", ""),
                        v.get("channel_id"),
                        v.get("thumbnail_url"),
                        v.get("duration"),
                        category,
                        v.get("published") or None,
                    ),
                )
                if cursor.rowcount > 0:
                    inserted += 1

                for child_id in child_ids:
                    self.conn.execute(
                        """INSERT OR IGNORE INTO child_video_access
                           (child_id, video_id, status, decided_at)
                           VALUES (?, ?, 'approved', datetime('now'))""",
                        (child_id, vid),
                    )

            self.conn.commit()
        return inserted

    def get_videos_missing_published_at(self, limit: int = 50) -> list[str]:
        """Return video_ids that have no published_at value (for backfill)."""
        with self._lock:
            cursor = self.conn.execute(
                "SELECT video_id FROM videos WHERE published_at IS NULL LIMIT ?",
                (limit,),
            )
            return [row[0] for row in cursor.fetchall()]

    def update_published_at(self, video_id: str, published_at: int) -> None:
        """Set published_at for a video."""
        with self._lock:
            self.conn.execute(
                "UPDATE videos SET published_at = ? WHERE video_id = ? AND published_at IS NULL",
                (published_at, video_id),
            )
            self.conn.commit()

    def update_description(self, video_id: str, description: str) -> None:
        """Set description for a video."""
        with self._lock:
            self.conn.execute(
                "UPDATE videos SET description = ? WHERE video_id = ?",
                (description, video_id),
            )
            self.conn.commit()

    # ── Per-Child Video Access ──────────────────────────────────────

    def request_video(self, child_id: int, video_id: str) -> str:
        """Request access to a video for a child.

        Returns the status: 'pending', 'approved', 'denied', or 'auto_approved'.

        Uses INSERT OR IGNORE to be truly atomic — no race window between
        a SELECT check and a subsequent INSERT.
        """
        with self._lock:
            # Determine desired status based on channel lists
            video = self.conn.execute(
                "SELECT channel_name FROM videos WHERE video_id = ?", (video_id,)
            ).fetchone()

            target_status = "pending"
            decided_at = None

            if video:
                blocked = self.conn.execute(
                    "SELECT 1 FROM child_channels WHERE child_id = ? AND channel_name = ? COLLATE NOCASE AND status = 'blocked'",
                    (child_id, video["channel_name"]),
                ).fetchone()
                if blocked:
                    target_status = "denied"
                    decided_at = "datetime('now')"
                else:
                    allowed = self.conn.execute(
                        "SELECT 1 FROM child_channels WHERE child_id = ? AND channel_name = ? COLLATE NOCASE AND status = 'allowed'",
                        (child_id, video["channel_name"]),
                    ).fetchone()
                    if allowed:
                        target_status = "auto_approved"
                        decided_at = "datetime('now')"

            # Atomic insert — if the row already exists, nothing happens
            if decided_at:
                cursor = self.conn.execute(
                    """INSERT OR IGNORE INTO child_video_access
                       (child_id, video_id, status, decided_at)
                       VALUES (?, ?, ?, datetime('now'))""",
                    (child_id, video_id, "approved" if target_status == "auto_approved" else target_status),
                )
            else:
                cursor = self.conn.execute(
                    "INSERT OR IGNORE INTO child_video_access (child_id, video_id, status) VALUES (?, ?, ?)",
                    (child_id, video_id, target_status),
                )
            self.conn.commit()

            if cursor.rowcount == 0:
                # Row already existed — return existing status
                row = self.conn.execute(
                    "SELECT status FROM child_video_access WHERE child_id = ? AND video_id = ?",
                    (child_id, video_id),
                ).fetchone()
                return row[0] if row else "pending"

            return target_status

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

    _SORT_CLAUSES = {
        "newest": "v.published_at IS NULL, v.published_at DESC",
        "oldest": "v.published_at IS NULL, v.published_at ASC",
        "title": "v.title COLLATE NOCASE ASC",
        "channel": "v.channel_name COLLATE NOCASE ASC, v.title COLLATE NOCASE ASC",
    }

    # Templates for generating order clauses with explicit direction
    _SORT_ORDER_TEMPLATES = {
        "newest": "v.published_at IS NULL, v.published_at {dir}",
        "oldest": "v.published_at IS NULL, v.published_at {dir}",
        "title": "v.title COLLATE NOCASE {dir}",
        "channel": "v.channel_name COLLATE NOCASE {dir}, v.title COLLATE NOCASE {dir}",
    }

    def get_approved_videos(self, child_id: int, category: Optional[str] = None,
                            channel: Optional[str] = None,
                            sort_by: str = "newest",
                            sort_order: Optional[str] = None,
                            watch_status: Optional[str] = None,
                            offset: int = 0, limit: int = 24) -> tuple[list[dict], int, dict]:
        """Get paginated approved videos for a child.

        Returns (videos, total_count, status_counts).
        """
        with self._lock:
            where_parts = [
                "cva.status = 'approved'",
                "cva.child_id = ?",
                "COALESCE(ch.status, 'allowed') != 'blocked'",
            ]
            params: list = [child_id]

            if category:
                where_parts.append("COALESCE(v.category, ch.category, 'fun') = ?")
                params.append(category)
            if channel:
                where_parts.append("v.channel_name = ? COLLATE NOCASE")
                params.append(channel)

            base_where = " AND ".join(where_parts)
            base_params = list(params)

            # Status counts (before watch_status filter)
            _from_join = """FROM child_video_access cva
                    JOIN videos v ON cva.video_id = v.video_id
                    LEFT JOIN child_channels ch
                        ON v.channel_name = ch.channel_name COLLATE NOCASE
                        AND ch.child_id = cva.child_id"""

            counts_row = self.conn.execute(
                f"""SELECT COUNT(*),
                           SUM(CASE WHEN cva.watch_status IS NULL THEN 1 ELSE 0 END),
                           SUM(CASE WHEN cva.watch_status = 'in_progress' THEN 1 ELSE 0 END),
                           SUM(CASE WHEN cva.watch_status = 'watched' THEN 1 ELSE 0 END)
                    {_from_join}
                    WHERE {base_where}""",
                base_params,
            ).fetchone()
            status_counts = {
                "all": counts_row[0] or 0,
                "unwatched": counts_row[1] or 0,
                "in_progress": counts_row[2] or 0,
                "watched": counts_row[3] or 0,
            }

            # Apply watch_status filter
            if watch_status == "unwatched":
                where_parts.append("cva.watch_status IS NULL")
            elif watch_status in ("in_progress", "watched"):
                where_parts.append("cva.watch_status = ?")
                params.append(watch_status)

            where_clause = " AND ".join(where_parts)

            count_row = self.conn.execute(
                f"""SELECT COUNT(*) {_from_join}
                    WHERE {where_clause}""",
                params,
            ).fetchone()
            total = count_row[0] if count_row else 0

            if sort_order and sort_order in ("asc", "desc"):
                direction = sort_order.upper()
                template = self._SORT_ORDER_TEMPLATES.get(
                    sort_by, self._SORT_ORDER_TEMPLATES["newest"]
                )
                order_clause = template.format(dir=direction)
            else:
                order_clause = self._SORT_CLAUSES.get(sort_by, self._SORT_CLAUSES["newest"])

            cursor = self.conn.execute(
                f"""SELECT v.*, COALESCE(v.category, ch.category, 'fun') as effective_category,
                           cva.decided_at as access_decided_at,
                           cva.watch_position, cva.watch_duration, cva.last_watched_at,
                           cva.watch_status
                    {_from_join}
                    WHERE {where_clause}
                    ORDER BY {order_clause}
                    LIMIT ? OFFSET ?""",
                params + [limit, offset],
            )
            return [dict(row) for row in cursor.fetchall()], total, status_counts

    # ── Watch Position (Resume Playback) ─────────────────────────────

    def save_watch_position(self, child_id: int, video_id: str,
                            position: int, duration: int,
                            auto_complete_threshold: int = 30) -> Optional[str]:
        """Save playback position for a child+video pair.

        Returns the watch_status after save ('in_progress', 'watched'),
        or None if no access row exists.

        Auto-completes (marks as 'watched') when position is within
        auto_complete_threshold seconds of the end.
        """
        with self._lock:
            # Auto-complete: near the end of the video
            if duration > 0 and position > 0 and (duration - position) <= auto_complete_threshold:
                cursor = self.conn.execute(
                    """UPDATE child_video_access
                       SET watch_position = 0, watch_duration = ?,
                           last_watched_at = datetime('now'),
                           watch_status = 'watched'
                       WHERE child_id = ? AND video_id = ?""",
                    (duration, child_id, video_id),
                )
                self.conn.commit()
                return "watched" if cursor.rowcount > 0 else None
            elif position > 0:
                cursor = self.conn.execute(
                    """UPDATE child_video_access
                       SET watch_position = ?, watch_duration = ?,
                           last_watched_at = datetime('now'),
                           watch_status = 'in_progress'
                       WHERE child_id = ? AND video_id = ?""",
                    (position, duration, child_id, video_id),
                )
                self.conn.commit()
                return "in_progress" if cursor.rowcount > 0 else None
            else:
                cursor = self.conn.execute(
                    """UPDATE child_video_access
                       SET watch_position = ?, watch_duration = ?,
                           last_watched_at = datetime('now')
                       WHERE child_id = ? AND video_id = ?""",
                    (position, duration, child_id, video_id),
                )
                self.conn.commit()
                if cursor.rowcount == 0:
                    return None
                # Return existing status
                row = self.conn.execute(
                    "SELECT watch_status FROM child_video_access WHERE child_id = ? AND video_id = ?",
                    (child_id, video_id),
                ).fetchone()
                return row[0] if row else None

    def get_watch_position(self, child_id: int, video_id: str) -> Optional[dict]:
        """Get saved playback position for a child+video pair.

        Returns dict with watch_position, watch_duration, last_watched_at,
        watch_status or None if no access row exists.
        """
        with self._lock:
            row = self.conn.execute(
                """SELECT watch_position, watch_duration, last_watched_at, watch_status
                   FROM child_video_access
                   WHERE child_id = ? AND video_id = ?""",
                (child_id, video_id),
            ).fetchone()
            if not row:
                return None
            return {
                "watch_position": row[0] or 0,
                "watch_duration": row[1] or 0,
                "last_watched_at": row[2],
                "watch_status": row[3],
            }

    def set_watch_status(self, child_id: int, video_id: str, status: str) -> bool:
        """Manually set watch_status for a child+video pair.

        If marking as unwatched (status is None or empty), clears position data.
        Returns True if a matching access row existed and was updated.
        """
        with self._lock:
            if not status:
                cursor = self.conn.execute(
                    """UPDATE child_video_access
                       SET watch_status = NULL, watch_position = 0,
                           watch_duration = 0, last_watched_at = NULL
                       WHERE child_id = ? AND video_id = ?""",
                    (child_id, video_id),
                )
            else:
                cursor = self.conn.execute(
                    """UPDATE child_video_access
                       SET watch_status = ?
                       WHERE child_id = ? AND video_id = ?""",
                    (status, child_id, video_id),
                )
            self.conn.commit()
            return cursor.rowcount > 0

    def clear_watch_position(self, child_id: int, video_id: str) -> bool:
        """Clear saved playback position (e.g. when video is finished)."""
        with self._lock:
            cursor = self.conn.execute(
                """UPDATE child_video_access
                   SET watch_position = 0, watch_duration = 0, last_watched_at = NULL
                   WHERE child_id = ? AND video_id = ?""",
                (child_id, video_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0

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

    # ── Channel Allow/Block Lists (Per-Child) ─────────────────────

    def add_channel(
        self, child_id: int, name: str, status: str,
        channel_id: Optional[str] = None,
        handle: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        """Add or update a channel in a child's allow/block list."""
        with self._lock:
            self.conn.execute(
                """INSERT INTO child_channels
                   (child_id, channel_name, status, channel_id, handle, category)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(child_id, channel_name) DO UPDATE SET
                       status = ?,
                       channel_id = COALESCE(?, channel_id),
                       handle = COALESCE(?, handle),
                       category = COALESCE(?, category),
                       added_at = datetime('now')""",
                (child_id, name, status, channel_id, handle, category,
                 status, channel_id, handle, category),
            )
            # Retroactively deny all approved/pending videos from this channel for this child
            if status == "blocked":
                self.conn.execute(
                    """UPDATE child_video_access SET status = 'denied', decided_at = datetime('now')
                       WHERE child_id = ? AND status IN ('approved', 'pending')
                         AND video_id IN (
                             SELECT video_id FROM videos
                             WHERE channel_name = ? COLLATE NOCASE
                         )""",
                    (child_id, name),
                )
            self.conn.commit()
            return True

    def add_channel_for_all(
        self, name: str, status: str,
        channel_id: Optional[str] = None,
        handle: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        """Add or update a channel for ALL children at once."""
        children = self.get_children()
        if not children:
            return False
        for child in children:
            self.add_channel(child["id"], name, status,
                             channel_id=channel_id, handle=handle, category=category)
        return True

    def remove_channel(self, child_id: int, name_or_handle: str) -> tuple[bool, int]:
        """Remove a channel from a child's list by name or @handle.

        Also revokes (deletes) all video access entries for that channel's
        videos so they no longer appear in the child's catalog.

        Returns (success, video_count) where video_count is the number of
        deleted video access rows.
        """
        with self._lock:
            # Look up the channel_name before deleting
            row = self.conn.execute(
                """SELECT channel_name FROM child_channels
                   WHERE child_id = ?
                     AND (channel_name = ? COLLATE NOCASE OR handle = ? COLLATE NOCASE)""",
                (child_id, name_or_handle, name_or_handle),
            ).fetchone()
            if not row:
                return (False, 0)

            channel_name = row[0]

            # Remove video access entries for this channel's videos
            cursor = self.conn.execute(
                """DELETE FROM child_video_access
                   WHERE child_id = ?
                     AND video_id IN (
                         SELECT video_id FROM videos
                         WHERE channel_name = ? COLLATE NOCASE
                     )""",
                (child_id, channel_name),
            )
            video_count = cursor.rowcount

            # Remove the channel entry
            self.conn.execute(
                """DELETE FROM child_channels
                   WHERE child_id = ? AND channel_name = ? COLLATE NOCASE""",
                (child_id, channel_name),
            )
            self.conn.commit()
            return (True, video_count)

    def count_channel_videos(self, child_id: int, channel_name: str) -> int:
        """Count video access entries for a channel for a given child."""
        with self._lock:
            row = self.conn.execute(
                """SELECT COUNT(*) FROM child_video_access
                   WHERE child_id = ?
                     AND video_id IN (
                         SELECT video_id FROM videos
                         WHERE channel_name = ? COLLATE NOCASE
                     )""",
                (child_id, channel_name),
            ).fetchone()
            return row[0] if row else 0

    def get_channels(self, child_id: int, status: Optional[str] = None) -> list[dict]:
        """List channels for a child, optionally filtered by status."""
        with self._lock:
            if status:
                cursor = self.conn.execute(
                    "SELECT * FROM child_channels WHERE child_id = ? AND status = ? ORDER BY channel_name",
                    (child_id, status),
                )
            else:
                cursor = self.conn.execute(
                    "SELECT * FROM child_channels WHERE child_id = ? ORDER BY channel_name",
                    (child_id,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def is_channel_allowed(self, child_id: int, name: str) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT 1 FROM child_channels WHERE child_id = ? AND channel_name = ? COLLATE NOCASE AND status = 'allowed'",
                (child_id, name),
            ).fetchone()
            return row is not None

    def is_channel_blocked(self, child_id: int, name: str) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT 1 FROM child_channels WHERE child_id = ? AND channel_name = ? COLLATE NOCASE AND status = 'blocked'",
                (child_id, name),
            ).fetchone()
            return row is not None

    # ── Channel Requests ─────────────────────────────────────────────

    def request_channel(self, child_id: int, channel_id: str, channel_name: str) -> str:
        """Request a channel for a child.

        Returns 'approved', 'denied', or 'pending'.
        If the channel is already allowed/blocked, returns immediately.
        """
        with self._lock:
            # Check allowed/blocked by channel name
            blocked = self.conn.execute(
                "SELECT 1 FROM child_channels WHERE child_id = ? AND channel_name = ? COLLATE NOCASE AND status = 'blocked'",
                (child_id, channel_name),
            ).fetchone()
            if blocked:
                return "denied"

            allowed = self.conn.execute(
                "SELECT 1 FROM child_channels WHERE child_id = ? AND channel_name = ? COLLATE NOCASE AND status = 'allowed'",
                (child_id, channel_name),
            ).fetchone()
            if allowed:
                return "approved"

            # Insert request (idempotent)
            cursor = self.conn.execute(
                """INSERT OR IGNORE INTO channel_requests
                   (child_id, channel_id, channel_name)
                   VALUES (?, ?, ?)""",
                (child_id, channel_id, channel_name),
            )
            self.conn.commit()

            if cursor.rowcount == 0:
                # Row already existed — return existing status
                row = self.conn.execute(
                    "SELECT status FROM channel_requests WHERE child_id = ? AND channel_id = ?",
                    (child_id, channel_id),
                ).fetchone()
                return row[0] if row else "pending"

            return "pending"

    def get_channel_request_status(self, child_id: int, channel_id: str) -> Optional[str]:
        """Get a child's channel request status. Returns status or None."""
        with self._lock:
            row = self.conn.execute(
                "SELECT status FROM channel_requests WHERE child_id = ? AND channel_id = ?",
                (child_id, channel_id),
            ).fetchone()
            return row[0] if row else None

    def update_channel_request_status(self, child_id: int, channel_id: str, status: str) -> bool:
        """Update a channel request status. Returns True if updated."""
        with self._lock:
            cursor = self.conn.execute(
                """UPDATE channel_requests
                   SET status = ?, decided_at = datetime('now')
                   WHERE child_id = ? AND channel_id = ?""",
                (status, child_id, channel_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0

    def get_pending_channel_request(self, child_id: int, channel_id: str) -> Optional[dict]:
        """Get a pending channel request row. Returns dict or None."""
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM channel_requests WHERE child_id = ? AND channel_id = ?",
                (child_id, channel_id),
            ).fetchone()
            return dict(row) if row else None

    def get_blocked_channels_set(self, child_id: int) -> set[str]:
        with self._lock:
            cursor = self.conn.execute(
                "SELECT channel_name FROM child_channels WHERE child_id = ? AND status = 'blocked'",
                (child_id,),
            )
            return {row[0].lower() for row in cursor.fetchall()}

    def get_channels_due_for_refresh(self, child_id: int, interval_hours: int = 6) -> list[dict]:
        """Return allowed channels for a child that haven't been refreshed within interval_hours."""
        with self._lock:
            cursor = self.conn.execute(
                """SELECT * FROM child_channels
                   WHERE child_id = ? AND status = 'allowed' AND channel_id IS NOT NULL
                     AND (last_refreshed_at IS NULL
                          OR last_refreshed_at < datetime('now', ? || ' hours'))
                   ORDER BY last_refreshed_at ASC NULLS FIRST""",
                (child_id, str(-interval_hours)),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_child_ids_for_channel(self, channel_name: str) -> list[int]:
        """Return child IDs that have the given channel allowed."""
        with self._lock:
            cursor = self.conn.execute(
                """SELECT child_id FROM child_channels
                   WHERE channel_name = ? COLLATE NOCASE AND status = 'allowed'""",
                (channel_name,),
            )
            return [row[0] for row in cursor.fetchall()]

    def get_all_channels_due_for_refresh(self, interval_hours: int = 6) -> list[dict]:
        """Return distinct allowed channels across all children due for refresh."""
        with self._lock:
            cursor = self.conn.execute(
                """SELECT channel_name, channel_id, category,
                          MIN(last_refreshed_at) as last_refreshed_at
                   FROM child_channels
                   WHERE status = 'allowed' AND channel_id IS NOT NULL
                     AND (last_refreshed_at IS NULL
                          OR last_refreshed_at < datetime('now', ? || ' hours'))
                   GROUP BY channel_id
                   ORDER BY last_refreshed_at ASC NULLS FIRST""",
                (str(-interval_hours),),
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_channel_refreshed_at(self, child_id: int, channel_name: str) -> None:
        """Stamp the current time as last_refreshed_at for a child's channel."""
        with self._lock:
            self.conn.execute(
                """UPDATE child_channels SET last_refreshed_at = datetime('now')
                   WHERE child_id = ? AND channel_name = ? COLLATE NOCASE""",
                (child_id, channel_name),
            )
            self.conn.commit()

    def update_all_channels_refreshed_at(self, channel_name: str) -> None:
        """Stamp last_refreshed_at for a channel across all children."""
        with self._lock:
            self.conn.execute(
                """UPDATE child_channels SET last_refreshed_at = datetime('now')
                   WHERE channel_name = ? COLLATE NOCASE""",
                (channel_name,),
            )
            self.conn.commit()

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
