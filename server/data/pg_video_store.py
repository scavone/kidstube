"""PostgreSQL-backed data layer — mirrors SQLiteVideoStore interface.

Uses psycopg2 with a single connection protected by threading.Lock,
matching the SQLite backend's threading model.

Datetime values are stored as ISO-format TEXT strings
('YYYY-MM-DD HH24:MI:SS') so data is format-compatible with the
SQLite backend and existing comparisons work without changes.

Case-insensitive uniqueness (SQLite COLLATE NOCASE) is replicated via
unique indexes on LOWER(col) expressions, which also serve as inference
targets for ON CONFLICT clauses.
"""

import hashlib
import secrets
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from data.base_store import BaseVideoStore

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.errors
except ImportError:
    psycopg2 = None  # type: ignore


# ── Datetime helpers ─────────────────────────────────────────────────────────

def _now() -> str:
    """Current UTC time as ISO string matching SQLite's datetime('now')."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _future_mins(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def _past_hours(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


class PostgresVideoStore(BaseVideoStore):
    """PostgreSQL backend for video approval, child profiles, and watch tracking."""

    _SORT_CLAUSES = {
        "newest": "v.published_at IS NULL, v.published_at DESC",
        "oldest": "v.published_at IS NULL, v.published_at ASC",
        "title": "LOWER(v.title) ASC",
        "channel": "LOWER(v.channel_name) ASC, LOWER(v.title) ASC",
    }

    _SORT_ORDER_TEMPLATES = {
        "newest": "v.published_at IS NULL, v.published_at {dir}",
        "oldest": "v.published_at IS NULL, v.published_at {dir}",
        "title": "LOWER(v.title) {dir}",
        "channel": "LOWER(v.channel_name) {dir}, LOWER(v.title) {dir}",
    }

    def __init__(self, url: str, avatar_base_path: str = "db"):
        if psycopg2 is None:
            raise ImportError(
                "psycopg2-binary is required for PostgreSQL support. "
                "Run: pip install psycopg2-binary"
            )
        self._lock = threading.Lock()
        self._url = url
        self._avatar_base = Path(avatar_base_path)
        self.conn = psycopg2.connect(url)
        self.conn.autocommit = False
        self._create_tables()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _cur(self):
        """Return a RealDictCursor (rows behave like dicts)."""
        return self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def _create_tables(self) -> None:
        _now_default = "TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')"
        stmts = [
            f"""CREATE TABLE IF NOT EXISTS children (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                avatar TEXT DEFAULT '👦',
                created_at TEXT NOT NULL DEFAULT {_now_default}
            )""",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_children_name_ci ON children (LOWER(name))",

            f"""CREATE TABLE IF NOT EXISTS child_settings (
                child_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT {_now_default},
                PRIMARY KEY (child_id, key),
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
            )""",

            f"""CREATE TABLE IF NOT EXISTS videos (
                id SERIAL PRIMARY KEY,
                video_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                channel_id TEXT,
                thumbnail_url TEXT,
                duration INTEGER,
                category TEXT,
                published_at INTEGER,
                description TEXT,
                requested_at TEXT NOT NULL DEFAULT {_now_default}
            )""",

            f"""CREATE TABLE IF NOT EXISTS child_video_access (
                child_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                requested_at TEXT NOT NULL DEFAULT {_now_default},
                decided_at TEXT,
                watch_position INTEGER DEFAULT 0,
                watch_duration INTEGER DEFAULT 0,
                last_watched_at TEXT,
                watch_status TEXT,
                PRIMARY KEY (child_id, video_id),
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
            )""",

            f"""CREATE TABLE IF NOT EXISTS watch_log (
                id SERIAL PRIMARY KEY,
                video_id TEXT NOT NULL,
                child_id INTEGER NOT NULL,
                duration INTEGER NOT NULL,
                category TEXT NOT NULL DEFAULT 'fun',
                watched_at TEXT NOT NULL DEFAULT {_now_default},
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_watch_log_date ON watch_log(watched_at)",
            "CREATE INDEX IF NOT EXISTS idx_watch_log_child ON watch_log(child_id, watched_at)",
            "CREATE INDEX IF NOT EXISTS idx_child_video_access_status ON child_video_access(status)",

            # Legacy global channels table (kept for migration; unused by new code)
            f"""CREATE TABLE IF NOT EXISTS channels (
                id SERIAL PRIMARY KEY,
                channel_name TEXT NOT NULL,
                channel_id TEXT,
                handle TEXT,
                status TEXT NOT NULL DEFAULT 'allowed',
                category TEXT,
                added_at TEXT NOT NULL DEFAULT {_now_default},
                last_refreshed_at TEXT
            )""",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_channels_name_ci ON channels (LOWER(channel_name))",

            # Per-child channels: case-insensitive uniqueness via expression index
            f"""CREATE TABLE IF NOT EXISTS child_channels (
                child_id INTEGER NOT NULL,
                channel_name TEXT NOT NULL,
                channel_id TEXT,
                handle TEXT,
                status TEXT NOT NULL DEFAULT 'allowed',
                category TEXT,
                added_at TEXT NOT NULL DEFAULT {_now_default},
                last_refreshed_at TEXT,
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
            )""",
            """CREATE UNIQUE INDEX IF NOT EXISTS uq_child_channels_ci
               ON child_channels (child_id, LOWER(channel_name))""",

            f"""CREATE TABLE IF NOT EXISTS channel_requests (
                child_id INTEGER NOT NULL,
                channel_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                requested_at TEXT NOT NULL DEFAULT {_now_default},
                decided_at TEXT,
                PRIMARY KEY (child_id, channel_id),
                FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE
            )""",

            f"""CREATE TABLE IF NOT EXISTS word_filters (
                id SERIAL PRIMARY KEY,
                word TEXT NOT NULL UNIQUE,
                added_at TEXT NOT NULL DEFAULT {_now_default}
            )""",

            f"""CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT {_now_default}
            )""",

            f"""CREATE TABLE IF NOT EXISTS search_log (
                id SERIAL PRIMARY KEY,
                query TEXT NOT NULL,
                child_id INTEGER,
                result_count INTEGER NOT NULL DEFAULT 0,
                searched_at TEXT NOT NULL DEFAULT {_now_default}
            )""",
            "CREATE INDEX IF NOT EXISTS idx_search_log_date ON search_log(searched_at)",

            # pairing_sessions includes chat_id/message_id from the start (no migration needed)
            f"""CREATE TABLE IF NOT EXISTS pairing_sessions (
                id SERIAL PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                pin TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                device_name TEXT,
                device_api_key TEXT,
                created_at TEXT NOT NULL DEFAULT {_now_default},
                expires_at TEXT NOT NULL,
                confirmed_at TEXT,
                chat_id INTEGER,
                message_id INTEGER
            )""",

            f"""CREATE TABLE IF NOT EXISTS paired_devices (
                id SERIAL PRIMARY KEY,
                device_name TEXT NOT NULL,
                api_key TEXT NOT NULL UNIQUE,
                paired_at TEXT NOT NULL DEFAULT {_now_default},
                last_seen_at TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            )""",
        ]
        with self._cur() as cur:
            for stmt in stmts:
                cur.execute(stmt)
        self.conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """Apply schema migrations for pre-existing databases."""
        def get_columns(cur, table: str) -> set:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            )
            return {row["column_name"] for row in cur.fetchall()}

        def get_tables(cur) -> set:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            return {row["table_name"] for row in cur.fetchall()}

        with self._cur() as cur:
            tbl = get_tables(cur)

            if "channels" in tbl:
                ch_cols = get_columns(cur, "channels")
                if "last_refreshed_at" not in ch_cols:
                    cur.execute("ALTER TABLE channels ADD COLUMN last_refreshed_at TEXT")

            if "videos" in tbl:
                vid_cols = get_columns(cur, "videos")
                if "published_at" not in vid_cols:
                    cur.execute("ALTER TABLE videos ADD COLUMN published_at INTEGER")
                if "description" not in vid_cols:
                    cur.execute("ALTER TABLE videos ADD COLUMN description TEXT")

            if "child_video_access" in tbl:
                cva_cols = get_columns(cur, "child_video_access")
                if "watch_position" not in cva_cols:
                    cur.execute(
                        "ALTER TABLE child_video_access ADD COLUMN watch_position INTEGER DEFAULT 0"
                    )
                    cur.execute(
                        "ALTER TABLE child_video_access ADD COLUMN watch_duration INTEGER DEFAULT 0"
                    )
                    cur.execute(
                        "ALTER TABLE child_video_access ADD COLUMN last_watched_at TEXT"
                    )
                if "watch_status" not in cva_cols:
                    cur.execute(
                        "ALTER TABLE child_video_access ADD COLUMN watch_status TEXT"
                    )
                    cur.execute("""
                        UPDATE child_video_access SET watch_status = 'in_progress'
                        WHERE watch_status IS NULL AND watch_position > 0
                          AND watch_duration > 0 AND watch_position < watch_duration - 30
                    """)
                    cur.execute("""
                        UPDATE child_video_access SET watch_status = 'watched'
                        WHERE watch_status IS NULL AND watch_position > 0
                          AND watch_duration > 0 AND watch_position >= watch_duration - 30
                    """)

            if "watch_log" in tbl:
                wl_cols = get_columns(cur, "watch_log")
                if "category" not in wl_cols:
                    cur.execute(
                        "ALTER TABLE watch_log ADD COLUMN category TEXT NOT NULL DEFAULT 'fun'"
                    )

            if "pairing_sessions" in tbl:
                ps_cols = get_columns(cur, "pairing_sessions")
                if "chat_id" not in ps_cols:
                    cur.execute("ALTER TABLE pairing_sessions ADD COLUMN chat_id INTEGER")
                    cur.execute("ALTER TABLE pairing_sessions ADD COLUMN message_id INTEGER")

            # Migrate global channels → per-child channels
            if "child_channels" in tbl:
                cur.execute("SELECT id FROM children")
                children = cur.fetchall()
                cur.execute("SELECT * FROM channels")
                global_channels = cur.fetchall()
                if children and global_channels:
                    for child_row in children:
                        cid = child_row["id"]
                        for ch in global_channels:
                            cur.execute(
                                """INSERT INTO child_channels
                                   (child_id, channel_name, channel_id, handle, status,
                                    category, added_at, last_refreshed_at)
                                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                   ON CONFLICT (child_id, LOWER(channel_name)) DO NOTHING""",
                                (
                                    cid,
                                    ch["channel_name"],
                                    ch["channel_id"],
                                    ch["handle"],
                                    ch["status"],
                                    ch["category"],
                                    ch["added_at"],
                                    ch["last_refreshed_at"],
                                ),
                            )
        self.conn.commit()

    # ── Child Profiles ──────────────────────────────────────────────

    def add_child(self, name: str, avatar: str = "👦") -> Optional[dict]:
        with self._lock:
            try:
                with self._cur() as cur:
                    cur.execute(
                        """INSERT INTO children (name, avatar) VALUES (%s, %s)
                           ON CONFLICT (LOWER(name)) DO NOTHING
                           RETURNING id""",
                        (name, avatar),
                    )
                    row = cur.fetchone()
                    if row is None:
                        self.conn.rollback()
                        return None
                    child_id = row["id"]
                    cur.execute("SELECT * FROM children WHERE id = %s", (child_id,))
                    result = cur.fetchone()
                self.conn.commit()
                return dict(result) if result else None
            except Exception:
                self.conn.rollback()
                raise

    def get_children(self) -> list[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute("SELECT * FROM children ORDER BY name")
                return [dict(r) for r in cur.fetchall()]

    def get_child(self, child_id: int) -> Optional[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute("SELECT * FROM children WHERE id = %s", (child_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def get_child_by_name(self, name: str) -> Optional[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT * FROM children WHERE LOWER(name) = LOWER(%s)", (name,)
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_child(
        self,
        child_id: int,
        name: Optional[str] = None,
        avatar: Optional[str] = None,
    ) -> Optional[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute("SELECT * FROM children WHERE id = %s", (child_id,))
                child = cur.fetchone()
                if not child:
                    return None
                new_name = name if name is not None else child["name"]
                new_avatar = avatar if avatar is not None else child["avatar"]
                try:
                    cur.execute(
                        "UPDATE children SET name = %s, avatar = %s WHERE id = %s",
                        (new_name, new_avatar, child_id),
                    )
                    self.conn.commit()
                except psycopg2.errors.UniqueViolation:
                    self.conn.rollback()
                    return None
                cur.execute("SELECT * FROM children WHERE id = %s", (child_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def remove_child(self, child_id: int) -> bool:
        with self._lock:
            with self._cur() as cur:
                cur.execute("DELETE FROM children WHERE id = %s", (child_id,))
                affected = cur.rowcount
            self.conn.commit()
            return affected > 0

    def get_avatar_dir(self) -> Path:
        avatar_dir = self._avatar_base / "avatars"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        return avatar_dir

    def save_avatar(self, child_id: int, photo_bytes: bytes) -> bool:
        child = self.get_child(child_id)
        if not child:
            return False
        avatar_path = self.get_avatar_dir() / f"{child_id}.jpg"
        avatar_path.write_bytes(photo_bytes)
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "UPDATE children SET avatar = 'photo' WHERE id = %s",
                    (child_id,),
                )
            self.conn.commit()
        return True

    def get_avatar_path(self, child_id: int) -> Optional[Path]:
        avatar_path = self.get_avatar_dir() / f"{child_id}.jpg"
        return avatar_path if avatar_path.exists() else None

    def delete_avatar(self, child_id: int) -> None:
        avatar_path = self.get_avatar_dir() / f"{child_id}.jpg"
        if avatar_path.exists():
            avatar_path.unlink()

    # ── Child Settings ──────────────────────────────────────────────

    def get_child_setting(self, child_id: int, key: str, default: str = "") -> str:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT value FROM child_settings WHERE child_id = %s AND key = %s",
                    (child_id, key),
                )
                row = cur.fetchone()
                return row["value"] if row else default

    def set_child_setting(self, child_id: int, key: str, value: str) -> None:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """INSERT INTO child_settings (child_id, key, value)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (child_id, key)
                       DO UPDATE SET value = %s, updated_at = %s""",
                    (child_id, key, value, value, _now()),
                )
            self.conn.commit()

    def get_child_settings(self, child_id: int) -> dict[str, str]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT key, value FROM child_settings WHERE child_id = %s",
                    (child_id,),
                )
                return {row["key"]: row["value"] for row in cur.fetchall()}

    # ── Child PIN ────────────────────────────────────────────────────

    def set_child_pin(self, child_id: int, pin: str) -> None:
        salt = secrets.token_hex(16)
        pin_hash = hashlib.sha256(f"{salt}:{pin}".encode()).hexdigest()
        self.set_child_setting(child_id, "pin", f"{salt}:{pin_hash}")

    def has_child_pin(self, child_id: int) -> bool:
        return bool(self.get_child_setting(child_id, "pin"))

    def verify_child_pin(self, child_id: int, pin: str) -> bool:
        stored = self.get_child_setting(child_id, "pin")
        if not stored or ":" not in stored:
            return False
        salt, expected_hash = stored.split(":", 1)
        actual_hash = hashlib.sha256(f"{salt}:{pin}".encode()).hexdigest()
        return secrets.compare_digest(actual_hash, expected_hash)

    def delete_child_pin(self, child_id: int) -> bool:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "DELETE FROM child_settings WHERE child_id = %s AND key = 'pin'",
                    (child_id,),
                )
                affected = cur.rowcount
            self.conn.commit()
            return affected > 0

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
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """INSERT INTO videos
                       (video_id, title, channel_name, channel_id, thumbnail_url,
                        duration, category, published_at, description)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (video_id) DO NOTHING""",
                    (
                        video_id, title, channel_name, channel_id, thumbnail_url,
                        duration, category, published_at, description,
                    ),
                )
                cur.execute(
                    "SELECT * FROM videos WHERE video_id = %s", (video_id,)
                )
                row = cur.fetchone()
            self.conn.commit()
            return dict(row) if row else {}

    def get_video(self, video_id: str) -> Optional[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT * FROM videos WHERE video_id = %s", (video_id,)
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def bulk_import_channel_videos(
        self,
        videos: list[dict],
        category: str,
        child_ids: list[int],
    ) -> int:
        if not videos or not child_ids:
            return 0
        inserted = 0
        with self._lock:
            with self._cur() as cur:
                for v in videos:
                    vid = v.get("video_id")
                    if not vid:
                        continue
                    cur.execute(
                        """INSERT INTO videos
                           (video_id, title, channel_name, channel_id,
                            thumbnail_url, duration, category, published_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (video_id) DO NOTHING""",
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
                    if cur.rowcount > 0:
                        inserted += 1

                    for child_id in child_ids:
                        cur.execute(
                            """INSERT INTO child_video_access
                               (child_id, video_id, status, decided_at)
                               VALUES (%s, %s, 'approved', %s)
                               ON CONFLICT (child_id, video_id) DO NOTHING""",
                            (child_id, vid, _now()),
                        )
            self.conn.commit()
        return inserted

    def get_videos_missing_published_at(self, limit: int = 50) -> list[str]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT video_id FROM videos WHERE published_at IS NULL LIMIT %s",
                    (limit,),
                )
                return [row["video_id"] for row in cur.fetchall()]

    def update_published_at(self, video_id: str, published_at: int) -> None:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "UPDATE videos SET published_at = %s WHERE video_id = %s AND published_at IS NULL",
                    (published_at, video_id),
                )
            self.conn.commit()

    def update_description(self, video_id: str, description: str) -> None:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "UPDATE videos SET description = %s WHERE video_id = %s",
                    (description, video_id),
                )
            self.conn.commit()

    # ── Per-Child Video Access ──────────────────────────────────────

    def request_video(self, child_id: int, video_id: str) -> str:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT channel_name FROM videos WHERE video_id = %s", (video_id,)
                )
                video = cur.fetchone()

                target_status = "pending"
                decided_at = None

                if video:
                    cur.execute(
                        """SELECT 1 FROM child_channels
                           WHERE child_id = %s AND LOWER(channel_name) = LOWER(%s)
                             AND status = 'blocked'""",
                        (child_id, video["channel_name"]),
                    )
                    if cur.fetchone():
                        target_status = "denied"
                        decided_at = _now()
                    else:
                        cur.execute(
                            """SELECT 1 FROM child_channels
                               WHERE child_id = %s AND LOWER(channel_name) = LOWER(%s)
                                 AND status = 'allowed'""",
                            (child_id, video["channel_name"]),
                        )
                        if cur.fetchone():
                            target_status = "auto_approved"
                            decided_at = _now()

                db_status = "approved" if target_status == "auto_approved" else target_status
                if decided_at:
                    cur.execute(
                        """INSERT INTO child_video_access
                           (child_id, video_id, status, decided_at)
                           VALUES (%s, %s, %s, %s)
                           ON CONFLICT (child_id, video_id) DO NOTHING""",
                        (child_id, video_id, db_status, decided_at),
                    )
                else:
                    cur.execute(
                        """INSERT INTO child_video_access (child_id, video_id, status)
                           VALUES (%s, %s, %s)
                           ON CONFLICT (child_id, video_id) DO NOTHING""",
                        (child_id, video_id, target_status),
                    )
                affected = cur.rowcount
                self.conn.commit()

                if affected == 0:
                    cur.execute(
                        "SELECT status FROM child_video_access WHERE child_id = %s AND video_id = %s",
                        (child_id, video_id),
                    )
                    row = cur.fetchone()
                    return row["status"] if row else "pending"

                return target_status

    def get_video_status(self, child_id: int, video_id: str) -> Optional[str]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT status FROM child_video_access WHERE child_id = %s AND video_id = %s",
                    (child_id, video_id),
                )
                row = cur.fetchone()
                return row["status"] if row else None

    def update_video_status(self, child_id: int, video_id: str, status: str) -> bool:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """UPDATE child_video_access
                       SET status = %s, decided_at = %s
                       WHERE child_id = %s AND video_id = %s""",
                    (status, _now(), child_id, video_id),
                )
                affected = cur.rowcount
            self.conn.commit()
            return affected > 0

    def get_pending_requests(self, child_id: Optional[int] = None) -> list[dict]:
        with self._lock:
            with self._cur() as cur:
                if child_id is not None:
                    cur.execute(
                        """SELECT cva.*, v.title, v.channel_name, v.thumbnail_url, v.duration,
                                  c.name as child_name
                           FROM child_video_access cva
                           JOIN videos v ON cva.video_id = v.video_id
                           JOIN children c ON cva.child_id = c.id
                           WHERE cva.status = 'pending' AND cva.child_id = %s
                           ORDER BY cva.requested_at DESC""",
                        (child_id,),
                    )
                else:
                    cur.execute(
                        """SELECT cva.*, v.title, v.channel_name, v.thumbnail_url, v.duration,
                                  c.name as child_name
                           FROM child_video_access cva
                           JOIN videos v ON cva.video_id = v.video_id
                           JOIN children c ON cva.child_id = c.id
                           WHERE cva.status = 'pending'
                           ORDER BY cva.requested_at DESC"""
                    )
                return [dict(r) for r in cur.fetchall()]

    def get_approved_videos(
        self,
        child_id: int,
        category: Optional[str] = None,
        channel: Optional[str] = None,
        sort_by: str = "newest",
        sort_order: Optional[str] = None,
        watch_status: Optional[str] = None,
        offset: int = 0,
        limit: int = 24,
    ) -> tuple[list[dict], int, dict]:
        with self._lock:
            where_parts = [
                "cva.status = 'approved'",
                "cva.child_id = %s",
                "COALESCE(ch.status, 'allowed') != 'blocked'",
            ]
            params: list = [child_id]

            if category:
                where_parts.append("COALESCE(v.category, ch.category, 'fun') = %s")
                params.append(category)
            if channel:
                where_parts.append(
                    "(LOWER(v.channel_name) = LOWER(%s) OR v.channel_id = %s)"
                )
                params.append(channel)
                params.append(channel)

            base_where = " AND ".join(where_parts)
            base_params = list(params)

            _from_join = """FROM child_video_access cva
                    JOIN videos v ON cva.video_id = v.video_id
                    LEFT JOIN child_channels ch
                        ON LOWER(v.channel_name) = LOWER(ch.channel_name)
                        AND ch.child_id = cva.child_id"""

            with self._cur() as cur:
                cur.execute(
                    f"""SELECT
                               COUNT(*) AS all_cnt,
                               SUM(CASE WHEN cva.watch_status IS NULL THEN 1 ELSE 0 END) AS unwatched_cnt,
                               SUM(CASE WHEN cva.watch_status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress_cnt,
                               SUM(CASE WHEN cva.watch_status = 'watched' THEN 1 ELSE 0 END) AS watched_cnt
                        {_from_join}
                        WHERE {base_where}""",
                    base_params,
                )
                counts_row = cur.fetchone()
                status_counts = {
                    "all": counts_row["all_cnt"] or 0,
                    "unwatched": counts_row["unwatched_cnt"] or 0,
                    "in_progress": counts_row["in_progress_cnt"] or 0,
                    "watched": counts_row["watched_cnt"] or 0,
                }

                if watch_status == "unwatched":
                    where_parts.append("cva.watch_status IS NULL")
                elif watch_status in ("in_progress", "watched"):
                    where_parts.append("cva.watch_status = %s")
                    params.append(watch_status)

                where_clause = " AND ".join(where_parts)

                cur.execute(
                    f"SELECT COUNT(*) AS cnt {_from_join} WHERE {where_clause}",
                    params,
                )
                total = (cur.fetchone() or {}).get("cnt", 0) or 0

                if sort_order and sort_order in ("asc", "desc"):
                    direction = sort_order.upper()
                    template = self._SORT_ORDER_TEMPLATES.get(
                        sort_by, self._SORT_ORDER_TEMPLATES["newest"]
                    )
                    order_clause = template.format(dir=direction)
                else:
                    order_clause = self._SORT_CLAUSES.get(
                        sort_by, self._SORT_CLAUSES["newest"]
                    )

                cur.execute(
                    f"""SELECT v.*,
                               COALESCE(v.category, ch.category, 'fun') as effective_category,
                               cva.decided_at as access_decided_at,
                               cva.watch_position, cva.watch_duration, cva.last_watched_at,
                               cva.watch_status
                        {_from_join}
                        WHERE {where_clause}
                        ORDER BY {order_clause}
                        LIMIT %s OFFSET %s""",
                    params + [limit, offset],
                )
                return [dict(r) for r in cur.fetchall()], total, status_counts

    def get_recently_added_videos(self, child_id: int, limit: int = 20) -> list[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT v.*,
                              COALESCE(v.category, ch.category, 'fun') as effective_category,
                              cva.decided_at as access_decided_at,
                              cva.watch_position, cva.watch_duration, cva.last_watched_at,
                              cva.watch_status
                       FROM child_video_access cva
                       JOIN videos v ON cva.video_id = v.video_id
                       LEFT JOIN child_channels ch
                           ON LOWER(v.channel_name) = LOWER(ch.channel_name)
                           AND ch.child_id = cva.child_id
                       WHERE cva.status = 'approved'
                         AND cva.child_id = %s
                         AND COALESCE(ch.status, 'allowed') != 'blocked'
                       ORDER BY cva.decided_at DESC NULLS LAST, cva.requested_at DESC
                       LIMIT %s""",
                    (child_id, limit),
                )
                return [dict(r) for r in cur.fetchall()]

    def get_channel_video_count(self, child_id: int, channel_id: str) -> int:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT COUNT(*) AS cnt FROM child_video_access cva
                       JOIN videos v ON cva.video_id = v.video_id
                       WHERE cva.child_id = %s AND cva.status = 'approved'
                         AND v.channel_id = %s""",
                    (child_id, channel_id),
                )
                row = cur.fetchone()
                return row["cnt"] if row else 0

    # ── Watch Position ───────────────────────────────────────────────

    def save_watch_position(
        self,
        child_id: int,
        video_id: str,
        position: int,
        duration: int,
        auto_complete_threshold: int = 30,
    ) -> Optional[str]:
        with self._lock:
            with self._cur() as cur:
                if (
                    duration > 0
                    and position > 0
                    and (duration - position) <= auto_complete_threshold
                ):
                    cur.execute(
                        """UPDATE child_video_access
                           SET watch_position = 0, watch_duration = %s,
                               last_watched_at = %s, watch_status = 'watched'
                           WHERE child_id = %s AND video_id = %s""",
                        (duration, _now(), child_id, video_id),
                    )
                    self.conn.commit()
                    return "watched" if cur.rowcount > 0 else None
                elif position > 0:
                    cur.execute(
                        """UPDATE child_video_access
                           SET watch_position = %s, watch_duration = %s,
                               last_watched_at = %s, watch_status = 'in_progress'
                           WHERE child_id = %s AND video_id = %s""",
                        (position, duration, _now(), child_id, video_id),
                    )
                    self.conn.commit()
                    return "in_progress" if cur.rowcount > 0 else None
                else:
                    cur.execute(
                        """UPDATE child_video_access
                           SET watch_position = %s, watch_duration = %s,
                               last_watched_at = %s
                           WHERE child_id = %s AND video_id = %s""",
                        (position, duration, _now(), child_id, video_id),
                    )
                    self.conn.commit()
                    if cur.rowcount == 0:
                        return None
                    cur.execute(
                        "SELECT watch_status FROM child_video_access WHERE child_id = %s AND video_id = %s",
                        (child_id, video_id),
                    )
                    row = cur.fetchone()
                    return row["watch_status"] if row else None

    def get_watch_position(self, child_id: int, video_id: str) -> Optional[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT watch_position, watch_duration, last_watched_at, watch_status
                       FROM child_video_access
                       WHERE child_id = %s AND video_id = %s""",
                    (child_id, video_id),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "watch_position": row["watch_position"] or 0,
                    "watch_duration": row["watch_duration"] or 0,
                    "last_watched_at": row["last_watched_at"],
                    "watch_status": row["watch_status"],
                }

    def set_watch_status(self, child_id: int, video_id: str, status: str) -> bool:
        with self._lock:
            with self._cur() as cur:
                if not status:
                    cur.execute(
                        """UPDATE child_video_access
                           SET watch_status = NULL, watch_position = 0,
                               watch_duration = 0, last_watched_at = NULL
                           WHERE child_id = %s AND video_id = %s""",
                        (child_id, video_id),
                    )
                else:
                    cur.execute(
                        """UPDATE child_video_access
                           SET watch_status = %s
                           WHERE child_id = %s AND video_id = %s""",
                        (status, child_id, video_id),
                    )
                affected = cur.rowcount
            self.conn.commit()
            return affected > 0

    def clear_watch_position(self, child_id: int, video_id: str) -> bool:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """UPDATE child_video_access
                       SET watch_position = 0, watch_duration = 0, last_watched_at = NULL
                       WHERE child_id = %s AND video_id = %s""",
                    (child_id, video_id),
                )
                affected = cur.rowcount
            self.conn.commit()
            return affected > 0

    # ── Session Windowing ─────────────────────────────────────────────

    def get_session_config(self, child_id: int) -> Optional[dict]:
        dur = self.get_child_setting(child_id, "session_duration_minutes", "")
        cooldown = self.get_child_setting(child_id, "session_cooldown_minutes", "")
        if not dur or not cooldown:
            return None
        try:
            max_str = self.get_child_setting(child_id, "session_max_per_day", "")
            return {
                "session_duration_minutes": int(dur),
                "cooldown_duration_minutes": int(cooldown),
                "max_sessions_per_day": int(max_str) if max_str else None,
            }
        except ValueError:
            return None

    def set_session_config(
        self,
        child_id: int,
        session_duration: int,
        cooldown_duration: int,
        max_sessions: Optional[int] = None,
    ) -> None:
        self.set_child_setting(child_id, "session_duration_minutes", str(session_duration))
        self.set_child_setting(child_id, "session_cooldown_minutes", str(cooldown_duration))
        if max_sessions is not None:
            self.set_child_setting(child_id, "session_max_per_day", str(max_sessions))
        else:
            with self._lock:
                with self._cur() as cur:
                    cur.execute(
                        "DELETE FROM child_settings WHERE child_id = %s AND key = 'session_max_per_day'",
                        (child_id,),
                    )
                self.conn.commit()

    def clear_session_config(self, child_id: int) -> None:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """DELETE FROM child_settings
                       WHERE child_id = %s AND key IN (
                           'session_duration_minutes',
                           'session_cooldown_minutes',
                           'session_max_per_day'
                       )""",
                    (child_id,),
                )
            self.conn.commit()

    # ── Watch Time ───────────────────────────────────────────────────

    def get_watch_log_for_day(self, child_id: int, utc_bounds: tuple) -> list:
        start, end = utc_bounds
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT duration, watched_at FROM watch_log
                       WHERE child_id = %s AND watched_at >= %s AND watched_at < %s
                       ORDER BY watched_at ASC""",
                    (child_id, start, end),
                )
                return [(row["duration"], row["watched_at"]) for row in cur.fetchall()]

    def record_watch_seconds(self, video_id: str, child_id: int, seconds: int) -> None:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT COALESCE(v.category, ch.category, 'fun') AS cat
                       FROM videos v
                       LEFT JOIN child_channels ch
                           ON LOWER(v.channel_name) = LOWER(ch.channel_name)
                           AND ch.child_id = %s
                       WHERE v.video_id = %s""",
                    (child_id, video_id),
                )
                row = cur.fetchone()
                category = row["cat"] if row else "fun"
                cur.execute(
                    "INSERT INTO watch_log (video_id, child_id, duration, category, watched_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (video_id, child_id, seconds, category, _now()),
                )
            self.conn.commit()

    def get_daily_watch_minutes(
        self,
        child_id: int,
        date_str: str,
        utc_bounds: Optional[tuple[str, str]] = None,
    ) -> float:
        start, end = utc_bounds if utc_bounds else (date_str, date_str)
        if utc_bounds:
            end_clause = "%s"
            end_param = end
        else:
            end_clause = "((%s::date + INTERVAL '1 day')::text)"
            end_param = end
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    f"""SELECT COALESCE(SUM(duration), 0) AS total FROM watch_log
                        WHERE child_id = %s AND watched_at >= %s AND watched_at < {end_clause}""",
                    (child_id, start, end_param),
                )
                row = cur.fetchone()
                return (row["total"] or 0) / 60.0

    def get_daily_watch_breakdown(
        self,
        child_id: int,
        date_str: str,
        utc_bounds: Optional[tuple[str, str]] = None,
    ) -> list[dict]:
        start, end = utc_bounds if utc_bounds else (date_str, date_str)
        if utc_bounds:
            end_clause = "%s"
            end_param = end
        else:
            end_clause = "((%s::date + INTERVAL '1 day')::text)"
            end_param = end
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    f"""SELECT w.video_id,
                               COALESCE(SUM(w.duration), 0) as total_sec,
                               v.title, v.channel_name, v.thumbnail_url,
                               v.duration as video_duration
                        FROM watch_log w
                        LEFT JOIN videos v ON w.video_id = v.video_id
                        WHERE w.child_id = %s AND w.watched_at >= %s AND w.watched_at < {end_clause}
                        GROUP BY w.video_id, v.title, v.channel_name, v.thumbnail_url, v.duration
                        ORDER BY total_sec DESC""",
                    (child_id, start, end_param),
                )
                return [
                    {
                        "video_id": row["video_id"],
                        "minutes": round((row["total_sec"] or 0) / 60.0, 1),
                        "title": row["title"] or row["video_id"],
                        "channel_name": row["channel_name"] or "Unknown",
                        "thumbnail_url": row["thumbnail_url"] or "",
                        "video_duration": row["video_duration"],
                    }
                    for row in cur.fetchall()
                ]

    # ── Category Time Limits ─────────────────────────────────────────

    def get_category_limits(self, child_id: int) -> dict[str, int]:
        settings = self.get_child_settings(child_id)
        prefix = "category_limit:"
        return {
            k[len(prefix):]: int(v)
            for k, v in settings.items()
            if k.startswith(prefix) and v
        }

    def set_category_limit(self, child_id: int, category: str, minutes: int) -> None:
        self.set_child_setting(child_id, f"category_limit:{category}", str(minutes))

    def clear_category_limit(self, child_id: int, category: str) -> None:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "DELETE FROM child_settings WHERE child_id = %s AND key = %s",
                    (child_id, f"category_limit:{category}"),
                )
            self.conn.commit()

    def get_daily_category_watch_minutes(
        self,
        child_id: int,
        date_str: str,
        category: str,
        utc_bounds: Optional[tuple[str, str]] = None,
    ) -> float:
        start, end = utc_bounds if utc_bounds else (date_str, date_str)
        if utc_bounds:
            end_clause = "%s"
            end_param = end
        else:
            end_clause = "((%s::date + INTERVAL '1 day')::text)"
            end_param = end
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    f"""SELECT COALESCE(SUM(duration), 0) AS total FROM watch_log
                        WHERE child_id = %s AND category = %s
                          AND watched_at >= %s AND watched_at < {end_clause}""",
                    (child_id, category, start, end_param),
                )
                row = cur.fetchone()
                return (row["total"] or 0) / 60.0

    def get_category_bonus(self, child_id: int, category: str, date: str) -> int:
        val = self.get_child_setting(child_id, f"bonus:{category}:{date}", "0")
        return int(val) if val else 0

    def add_category_bonus(
        self, child_id: int, category: str, minutes: int, date: str
    ) -> None:
        existing = self.get_category_bonus(child_id, category, date)
        self.set_child_setting(child_id, f"bonus:{category}:{date}", str(existing + minutes))

    def get_watched_categories_today(
        self, child_id: int, utc_bounds: tuple[str, str]
    ) -> list[str]:
        start, end = utc_bounds
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT DISTINCT category FROM watch_log
                       WHERE child_id = %s AND watched_at >= %s AND watched_at < %s""",
                    (child_id, start, end),
                )
                return [row["category"] for row in cur.fetchall()]

    def get_video_effective_category(self, video_id: str, child_id: int) -> str:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT COALESCE(v.category, ch.category, 'fun') AS cat
                       FROM videos v
                       LEFT JOIN child_channels ch
                           ON LOWER(v.channel_name) = LOWER(ch.channel_name)
                           AND ch.child_id = %s
                       WHERE v.video_id = %s""",
                    (child_id, video_id),
                )
                row = cur.fetchone()
                return row["cat"] if row else "fun"

    # ── Channels ─────────────────────────────────────────────────────

    def add_channel(
        self,
        child_id: int,
        name: str,
        status: str,
        channel_id: Optional[str] = None,
        handle: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """INSERT INTO child_channels
                       (child_id, channel_name, status, channel_id, handle, category, added_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (child_id, LOWER(channel_name)) DO UPDATE SET
                           status = EXCLUDED.status,
                           channel_id = COALESCE(EXCLUDED.channel_id, child_channels.channel_id),
                           handle = COALESCE(EXCLUDED.handle, child_channels.handle),
                           category = COALESCE(EXCLUDED.category, child_channels.category),
                           added_at = EXCLUDED.added_at""",
                    (child_id, name, status, channel_id, handle, category, _now()),
                )
                if status == "blocked":
                    cur.execute(
                        """UPDATE child_video_access
                           SET status = 'denied', decided_at = %s
                           WHERE child_id = %s AND status IN ('approved', 'pending')
                             AND video_id IN (
                                 SELECT video_id FROM videos
                                 WHERE LOWER(channel_name) = LOWER(%s)
                             )""",
                        (_now(), child_id, name),
                    )
            self.conn.commit()
            return True

    def add_channel_for_all(
        self,
        name: str,
        status: str,
        channel_id: Optional[str] = None,
        handle: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        children = self.get_children()
        if not children:
            return False
        for child in children:
            self.add_channel(
                child["id"], name, status,
                channel_id=channel_id, handle=handle, category=category,
            )
        return True

    def remove_channel(self, child_id: int, name_or_handle: str) -> tuple[bool, int]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT channel_name FROM child_channels
                       WHERE child_id = %s
                         AND (LOWER(channel_name) = LOWER(%s) OR LOWER(handle) = LOWER(%s))""",
                    (child_id, name_or_handle, name_or_handle),
                )
                row = cur.fetchone()
                if not row:
                    return (False, 0)
                channel_name = row["channel_name"]
                cur.execute(
                    """DELETE FROM child_video_access
                       WHERE child_id = %s
                         AND video_id IN (
                             SELECT video_id FROM videos
                             WHERE LOWER(channel_name) = LOWER(%s)
                         )""",
                    (child_id, channel_name),
                )
                video_count = cur.rowcount
                cur.execute(
                    """DELETE FROM child_channels
                       WHERE child_id = %s AND LOWER(channel_name) = LOWER(%s)""",
                    (child_id, channel_name),
                )
            self.conn.commit()
            return (True, video_count)

    def count_channel_videos(self, child_id: int, channel_name: str) -> int:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT COUNT(*) AS cnt FROM child_video_access
                       WHERE child_id = %s
                         AND video_id IN (
                             SELECT video_id FROM videos
                             WHERE LOWER(channel_name) = LOWER(%s)
                         )""",
                    (child_id, channel_name),
                )
                row = cur.fetchone()
                return row["cnt"] if row else 0

    def get_channels(self, child_id: int, status: Optional[str] = None) -> list[dict]:
        with self._lock:
            with self._cur() as cur:
                if status:
                    cur.execute(
                        "SELECT * FROM child_channels WHERE child_id = %s AND status = %s ORDER BY channel_name",
                        (child_id, status),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM child_channels WHERE child_id = %s ORDER BY channel_name",
                        (child_id,),
                    )
                return [dict(r) for r in cur.fetchall()]

    def get_channels_with_latest_video(self, child_id: int) -> list[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT cc.channel_name, cc.channel_id, cc.handle, cc.category,
                              v.video_id, v.title as video_title, v.thumbnail_url as video_thumbnail,
                              v.duration as video_duration, v.published_at as video_published_at
                       FROM child_channels cc
                       LEFT JOIN (
                           SELECT v2.channel_name, v2.video_id, v2.title, v2.thumbnail_url,
                                  v2.duration, v2.published_at,
                                  ROW_NUMBER() OVER (
                                      PARTITION BY LOWER(v2.channel_name)
                                      ORDER BY v2.published_at DESC NULLS LAST
                                  ) as rn
                           FROM videos v2
                           JOIN child_video_access cva ON v2.video_id = cva.video_id
                           WHERE cva.child_id = %s AND cva.status = 'approved'
                       ) v ON LOWER(v.channel_name) = LOWER(cc.channel_name) AND v.rn = 1
                       WHERE cc.child_id = %s AND cc.status = 'allowed'
                       ORDER BY v.published_at DESC NULLS LAST, cc.channel_name ASC""",
                    (child_id, child_id),
                )
                results = []
                for row in cur.fetchall():
                    channel = {
                        "channel_name": row["channel_name"],
                        "channel_id": row["channel_id"],
                        "handle": row["handle"],
                        "category": row["category"],
                    }
                    if row["video_id"]:
                        channel["latest_video"] = {
                            "video_id": row["video_id"],
                            "title": row["video_title"],
                            "thumbnail_url": row["video_thumbnail"],
                            "duration": row["video_duration"],
                            "published_at": row["video_published_at"],
                        }
                    else:
                        channel["latest_video"] = None
                    results.append(channel)
                return results

    def is_channel_allowed(self, child_id: int, name: str) -> bool:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT 1 FROM child_channels
                       WHERE child_id = %s AND LOWER(channel_name) = LOWER(%s)
                         AND status = 'allowed'""",
                    (child_id, name),
                )
                return cur.fetchone() is not None

    def is_channel_blocked(self, child_id: int, name: str) -> bool:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT 1 FROM child_channels
                       WHERE child_id = %s AND LOWER(channel_name) = LOWER(%s)
                         AND status = 'blocked'""",
                    (child_id, name),
                )
                return cur.fetchone() is not None

    # ── Channel Requests ─────────────────────────────────────────────

    def request_channel(self, child_id: int, channel_id: str, channel_name: str) -> str:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT 1 FROM child_channels
                       WHERE child_id = %s AND LOWER(channel_name) = LOWER(%s)
                         AND status = 'blocked'""",
                    (child_id, channel_name),
                )
                if cur.fetchone():
                    return "denied"
                cur.execute(
                    """SELECT 1 FROM child_channels
                       WHERE child_id = %s AND LOWER(channel_name) = LOWER(%s)
                         AND status = 'allowed'""",
                    (child_id, channel_name),
                )
                if cur.fetchone():
                    return "approved"
                cur.execute(
                    """INSERT INTO channel_requests (child_id, channel_id, channel_name)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (child_id, channel_id) DO NOTHING""",
                    (child_id, channel_id, channel_name),
                )
                affected = cur.rowcount
                self.conn.commit()
                if affected == 0:
                    cur.execute(
                        "SELECT status FROM channel_requests WHERE child_id = %s AND channel_id = %s",
                        (child_id, channel_id),
                    )
                    row = cur.fetchone()
                    return row["status"] if row else "pending"
                return "pending"

    def get_channel_request_status(
        self, child_id: int, channel_id: str
    ) -> Optional[str]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT status FROM channel_requests WHERE child_id = %s AND channel_id = %s",
                    (child_id, channel_id),
                )
                row = cur.fetchone()
                return row["status"] if row else None

    def update_channel_request_status(
        self, child_id: int, channel_id: str, status: str
    ) -> bool:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """UPDATE channel_requests
                       SET status = %s, decided_at = %s
                       WHERE child_id = %s AND channel_id = %s""",
                    (status, _now(), child_id, channel_id),
                )
                affected = cur.rowcount
            self.conn.commit()
            return affected > 0

    def get_pending_channel_request(
        self, child_id: int, channel_id: str
    ) -> Optional[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT * FROM channel_requests WHERE child_id = %s AND channel_id = %s",
                    (child_id, channel_id),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def get_blocked_channels_set(self, child_id: int) -> set[str]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT channel_name FROM child_channels WHERE child_id = %s AND status = 'blocked'",
                    (child_id,),
                )
                return {row["channel_name"].lower() for row in cur.fetchall()}

    def get_channels_due_for_refresh(
        self, child_id: int, interval_hours: int = 6
    ) -> list[dict]:
        cutoff = _past_hours(interval_hours)
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT * FROM child_channels
                       WHERE child_id = %s AND status = 'allowed' AND channel_id IS NOT NULL
                         AND (last_refreshed_at IS NULL OR last_refreshed_at < %s)
                       ORDER BY last_refreshed_at ASC NULLS FIRST""",
                    (child_id, cutoff),
                )
                return [dict(r) for r in cur.fetchall()]

    def get_child_ids_for_channel(self, channel_name: str) -> list[int]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT child_id FROM child_channels
                       WHERE LOWER(channel_name) = LOWER(%s) AND status = 'allowed'""",
                    (channel_name,),
                )
                return [row["child_id"] for row in cur.fetchall()]

    def get_all_channels_due_for_refresh(self, interval_hours: int = 6) -> list[dict]:
        cutoff = _past_hours(interval_hours)
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT channel_name, channel_id, category,
                              MIN(last_refreshed_at) as last_refreshed_at
                       FROM child_channels
                       WHERE status = 'allowed' AND channel_id IS NOT NULL
                         AND (last_refreshed_at IS NULL OR last_refreshed_at < %s)
                       GROUP BY channel_id, channel_name, category
                       ORDER BY last_refreshed_at ASC NULLS FIRST""",
                    (cutoff,),
                )
                return [dict(r) for r in cur.fetchall()]

    def update_channel_refreshed_at(self, child_id: int, channel_name: str) -> None:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """UPDATE child_channels SET last_refreshed_at = %s
                       WHERE child_id = %s AND LOWER(channel_name) = LOWER(%s)""",
                    (_now(), child_id, channel_name),
                )
            self.conn.commit()

    def update_all_channels_refreshed_at(self, channel_name: str) -> None:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """UPDATE child_channels SET last_refreshed_at = %s
                       WHERE LOWER(channel_name) = LOWER(%s)""",
                    (_now(), channel_name),
                )
            self.conn.commit()

    # ── Word Filters ─────────────────────────────────────────────────

    def add_word_filter(self, word: str) -> bool:
        with self._lock:
            try:
                with self._cur() as cur:
                    cur.execute(
                        "INSERT INTO word_filters (word) VALUES (%s) ON CONFLICT (word) DO NOTHING",
                        (word.lower(),),
                    )
                    affected = cur.rowcount
                self.conn.commit()
                return affected > 0
            except Exception:
                self.conn.rollback()
                return False

    def remove_word_filter(self, word: str) -> bool:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "DELETE FROM word_filters WHERE LOWER(word) = LOWER(%s)", (word,)
                )
                affected = cur.rowcount
            self.conn.commit()
            return affected > 0

    def get_word_filters(self) -> list[str]:
        with self._lock:
            with self._cur() as cur:
                cur.execute("SELECT word FROM word_filters ORDER BY word")
                return [row["word"] for row in cur.fetchall()]

    def get_word_filters_set(self) -> set[str]:
        with self._lock:
            with self._cur() as cur:
                cur.execute("SELECT word FROM word_filters")
                return {row["word"].lower() for row in cur.fetchall()}

    # ── Global Settings ─────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            with self._cur() as cur:
                cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
                row = cur.fetchone()
                return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """INSERT INTO settings (key, value) VALUES (%s, %s)
                       ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = %s""",
                    (key, value, value, _now()),
                )
            self.conn.commit()

    # ── Search Logging ──────────────────────────────────────────────

    def record_search(self, query: str, child_id: int, result_count: int) -> None:
        query = query[:200]
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "INSERT INTO search_log (query, child_id, result_count, searched_at) "
                    "VALUES (%s, %s, %s, %s)",
                    (query, child_id, result_count, _now()),
                )
            self.conn.commit()

    # ── Stats ───────────────────────────────────────────────────────

    def get_stats(self, child_id: Optional[int] = None) -> dict:
        with self._lock:
            with self._cur() as cur:
                if child_id is not None:
                    cur.execute(
                        """SELECT
                            COUNT(*) as total,
                            COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) as pending,
                            COALESCE(SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END), 0) as approved,
                            COALESCE(SUM(CASE WHEN status = 'denied' THEN 1 ELSE 0 END), 0) as denied
                           FROM child_video_access WHERE child_id = %s""",
                        (child_id,),
                    )
                else:
                    cur.execute(
                        """SELECT
                            COUNT(*) as total,
                            COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) as pending,
                            COALESCE(SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END), 0) as approved,
                            COALESCE(SUM(CASE WHEN status = 'denied' THEN 1 ELSE 0 END), 0) as denied
                           FROM child_video_access"""
                    )
                row = cur.fetchone()
                return (
                    dict(row) if row else {"total": 0, "pending": 0, "approved": 0, "denied": 0}
                )

    # ── Pairing ─────────────────────────────────────────────────────

    def create_pairing_session(
        self,
        device_name: Optional[str] = None,
        expiry_minutes: int = 5,
    ) -> dict:
        token = secrets.token_urlsafe(32)
        pin = f"{secrets.randbelow(1_000_000):06d}"
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """INSERT INTO pairing_sessions
                       (token, pin, device_name, expires_at, created_at)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (token, pin, device_name, _future_mins(expiry_minutes), _now()),
                )
                cur.execute(
                    "SELECT * FROM pairing_sessions WHERE token = %s", (token,)
                )
                row = cur.fetchone()
            self.conn.commit()
            return dict(row)

    def get_pairing_session(self, token: str) -> Optional[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT * FROM pairing_sessions WHERE token = %s", (token,)
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def get_pairing_session_by_pin(self, pin: str) -> Optional[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT * FROM pairing_sessions
                       WHERE pin = %s AND status = 'pending' AND expires_at > %s
                       ORDER BY created_at DESC LIMIT 1""",
                    (pin, _now()),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def confirm_pairing(
        self, token: str, device_name: Optional[str] = None
    ) -> Optional[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """SELECT * FROM pairing_sessions
                       WHERE token = %s AND status = 'pending' AND expires_at > %s""",
                    (token, _now()),
                )
                session = cur.fetchone()
                if not session:
                    return None
                device_api_key = secrets.token_urlsafe(48)
                name = device_name or session["device_name"] or "Apple TV"
                cur.execute(
                    """UPDATE pairing_sessions
                       SET status = 'confirmed', confirmed_at = %s
                       WHERE token = %s""",
                    (_now(), token),
                )
                cur.execute(
                    "INSERT INTO paired_devices (device_name, api_key, paired_at) VALUES (%s, %s, %s)",
                    (name, device_api_key, _now()),
                )
                cur.execute(
                    "SELECT * FROM paired_devices WHERE api_key = %s", (device_api_key,)
                )
                device = cur.fetchone()
            self.conn.commit()
            return dict(device)

    def deny_pairing(self, token: str) -> bool:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """UPDATE pairing_sessions SET status = 'denied'
                       WHERE token = %s AND status = 'pending'""",
                    (token,),
                )
                affected = cur.rowcount
            self.conn.commit()
            return affected > 0

    def set_pairing_device_key(self, token: str, api_key: str) -> None:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "UPDATE pairing_sessions SET device_api_key = %s WHERE token = %s",
                    (api_key, token),
                )
            self.conn.commit()

    def set_pairing_message_ids(
        self, token: str, chat_id: int, message_id: int
    ) -> None:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "UPDATE pairing_sessions SET chat_id = %s, message_id = %s WHERE token = %s",
                    (chat_id, message_id, token),
                )
            self.conn.commit()

    def get_paired_devices(self) -> list[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT id, device_name, paired_at, last_seen_at, is_active "
                    "FROM paired_devices ORDER BY paired_at DESC"
                )
                return [dict(r) for r in cur.fetchall()]

    def revoke_device(self, device_id: int) -> bool:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "UPDATE paired_devices SET is_active = 0 WHERE id = %s AND is_active = 1",
                    (device_id,),
                )
                affected = cur.rowcount
            self.conn.commit()
            return affected > 0

    def rename_device(self, device_id: int, name: str) -> bool:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "UPDATE paired_devices SET device_name = %s WHERE id = %s AND is_active = 1",
                    (name, device_id),
                )
                affected = cur.rowcount
            self.conn.commit()
            return affected > 0

    def get_device_by_api_key(self, api_key: str) -> Optional[dict]:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "SELECT * FROM paired_devices WHERE api_key = %s AND is_active = 1",
                    (api_key,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_device_last_seen(self, device_id: int) -> None:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    "UPDATE paired_devices SET last_seen_at = %s WHERE id = %s",
                    (_now(), device_id),
                )
            self.conn.commit()

    def cleanup_expired_pairing_sessions(self) -> int:
        with self._lock:
            with self._cur() as cur:
                cur.execute(
                    """DELETE FROM pairing_sessions
                       WHERE status = 'pending' AND expires_at <= %s""",
                    (_now(),),
                )
                affected = cur.rowcount
            self.conn.commit()
            return affected

    def close(self) -> None:
        self.conn.close()
