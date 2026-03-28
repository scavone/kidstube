"""Data layer package.

Provides `create_video_store()` factory that returns either the SQLite or
PostgreSQL backend based on the DatabaseConfig.
"""

from data.base_store import BaseVideoStore
from data.video_store import SQLiteVideoStore, VideoStore


def create_video_store(cfg) -> BaseVideoStore:
    """Return the appropriate VideoStore backend based on config.

    Args:
        cfg: DatabaseConfig with .type ("sqlite" | "postgres") and
             .path (SQLite file path) or .url (PostgreSQL DSN).

    Raises:
        ImportError: if type is "postgres" and psycopg2-binary is not installed.
        ValueError: if type is "postgres" but url is empty.
    """
    if cfg.type == "postgres":
        if not cfg.url:
            raise ValueError("BRG_DATABASE_URL must be set when BRG_DATABASE_TYPE=postgres")
        from data.pg_video_store import PostgresVideoStore
        return PostgresVideoStore(cfg.url)
    # Default: SQLite
    return SQLiteVideoStore(cfg.path)
