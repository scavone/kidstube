"""Abstract base interface for all VideoStore implementations.

Defines the contract that both SQLite and PostgreSQL backends must follow.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class BaseVideoStore(ABC):
    """Abstract base for all VideoStore backends."""

    # ── Child Profiles ──────────────────────────────────────────────

    @abstractmethod
    def add_child(self, name: str, avatar: str = "👦") -> Optional[dict]: ...

    @abstractmethod
    def get_children(self) -> list[dict]: ...

    @abstractmethod
    def get_child(self, child_id: int) -> Optional[dict]: ...

    @abstractmethod
    def get_child_by_name(self, name: str) -> Optional[dict]: ...

    @abstractmethod
    def update_child(self, child_id: int, name: Optional[str] = None,
                     avatar: Optional[str] = None) -> Optional[dict]: ...

    @abstractmethod
    def remove_child(self, child_id: int) -> bool: ...

    @abstractmethod
    def get_avatar_dir(self) -> Path: ...

    @abstractmethod
    def save_avatar(self, child_id: int, photo_bytes: bytes) -> bool: ...

    @abstractmethod
    def get_avatar_path(self, child_id: int) -> Optional[Path]: ...

    @abstractmethod
    def delete_avatar(self, child_id: int) -> None: ...

    # ── Child Settings ──────────────────────────────────────────────

    @abstractmethod
    def get_child_setting(self, child_id: int, key: str, default: str = "") -> str: ...

    @abstractmethod
    def set_child_setting(self, child_id: int, key: str, value: str) -> None: ...

    @abstractmethod
    def get_child_settings(self, child_id: int) -> dict[str, str]: ...

    # ── Child PIN ────────────────────────────────────────────────────

    @abstractmethod
    def set_child_pin(self, child_id: int, pin: str) -> None: ...

    @abstractmethod
    def has_child_pin(self, child_id: int) -> bool: ...

    @abstractmethod
    def verify_child_pin(self, child_id: int, pin: str) -> bool: ...

    @abstractmethod
    def delete_child_pin(self, child_id: int) -> bool: ...

    # ── Videos ──────────────────────────────────────────────────────

    @abstractmethod
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
    ) -> dict: ...

    @abstractmethod
    def get_video(self, video_id: str) -> Optional[dict]: ...

    @abstractmethod
    def bulk_import_channel_videos(
        self,
        videos: list[dict],
        category: str,
        child_ids: list[int],
    ) -> int: ...

    @abstractmethod
    def get_videos_missing_published_at(self, limit: int = 50) -> list[str]: ...

    @abstractmethod
    def update_published_at(self, video_id: str, published_at: int) -> None: ...

    @abstractmethod
    def update_description(self, video_id: str, description: str) -> None: ...

    # ── Per-Child Video Access ──────────────────────────────────────

    @abstractmethod
    def request_video(self, child_id: int, video_id: str) -> str: ...

    @abstractmethod
    def get_video_status(self, child_id: int, video_id: str) -> Optional[str]: ...

    @abstractmethod
    def update_video_status(self, child_id: int, video_id: str, status: str) -> bool: ...

    @abstractmethod
    def get_pending_requests(self, child_id: Optional[int] = None) -> list[dict]: ...

    @abstractmethod
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
    ) -> tuple[list[dict], int, dict]: ...

    @abstractmethod
    def get_recently_added_videos(self, child_id: int, limit: int = 20) -> list[dict]: ...

    @abstractmethod
    def get_channel_video_count(self, child_id: int, channel_id: str) -> int: ...

    # ── Watch Position ───────────────────────────────────────────────

    @abstractmethod
    def save_watch_position(
        self,
        child_id: int,
        video_id: str,
        position: int,
        duration: int,
        auto_complete_threshold: int = 30,
    ) -> Optional[str]: ...

    @abstractmethod
    def get_watch_position(self, child_id: int, video_id: str) -> Optional[dict]: ...

    @abstractmethod
    def set_watch_status(self, child_id: int, video_id: str, status: str) -> bool: ...

    @abstractmethod
    def clear_watch_position(self, child_id: int, video_id: str) -> bool: ...

    # ── Session Windowing ─────────────────────────────────────────────

    @abstractmethod
    def get_session_config(self, child_id: int) -> Optional[dict]: ...

    @abstractmethod
    def set_session_config(
        self,
        child_id: int,
        session_duration: int,
        cooldown_duration: int,
        max_sessions: Optional[int] = None,
    ) -> None: ...

    @abstractmethod
    def clear_session_config(self, child_id: int) -> None: ...

    # ── Watch Time ───────────────────────────────────────────────────

    @abstractmethod
    def get_watch_log_for_day(self, child_id: int, utc_bounds: tuple) -> list: ...

    @abstractmethod
    def record_watch_seconds(self, video_id: str, child_id: int, seconds: int) -> None: ...

    @abstractmethod
    def get_daily_watch_minutes(
        self,
        child_id: int,
        date_str: str,
        utc_bounds: Optional[tuple[str, str]] = None,
    ) -> float: ...

    @abstractmethod
    def get_daily_watch_breakdown(
        self,
        child_id: int,
        date_str: str,
        utc_bounds: Optional[tuple[str, str]] = None,
    ) -> list[dict]: ...

    # ── Category Time Limits ─────────────────────────────────────────

    @abstractmethod
    def get_category_limits(self, child_id: int) -> dict[str, int]: ...

    @abstractmethod
    def set_category_limit(self, child_id: int, category: str, minutes: int) -> None: ...

    @abstractmethod
    def clear_category_limit(self, child_id: int, category: str) -> None: ...

    @abstractmethod
    def get_daily_category_watch_minutes(
        self,
        child_id: int,
        date_str: str,
        category: str,
        utc_bounds: Optional[tuple[str, str]] = None,
    ) -> float: ...

    @abstractmethod
    def get_category_bonus(self, child_id: int, category: str, date: str) -> int: ...

    @abstractmethod
    def add_category_bonus(
        self, child_id: int, category: str, minutes: int, date: str
    ) -> None: ...

    @abstractmethod
    def get_watched_categories_today(
        self, child_id: int, utc_bounds: tuple[str, str]
    ) -> list[str]: ...

    @abstractmethod
    def get_video_effective_category(self, video_id: str, child_id: int) -> str: ...

    # ── Channels ─────────────────────────────────────────────────────

    @abstractmethod
    def add_channel(
        self,
        child_id: int,
        name: str,
        status: str,
        channel_id: Optional[str] = None,
        handle: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool: ...

    @abstractmethod
    def add_channel_for_all(
        self,
        name: str,
        status: str,
        channel_id: Optional[str] = None,
        handle: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool: ...

    @abstractmethod
    def remove_channel(self, child_id: int, name_or_handle: str) -> tuple[bool, int]: ...

    @abstractmethod
    def count_channel_videos(self, child_id: int, channel_name: str) -> int: ...

    @abstractmethod
    def get_channels(self, child_id: int, status: Optional[str] = None) -> list[dict]: ...

    @abstractmethod
    def get_channels_with_latest_video(self, child_id: int) -> list[dict]: ...

    @abstractmethod
    def is_channel_allowed(self, child_id: int, name: str) -> bool: ...

    @abstractmethod
    def is_channel_blocked(self, child_id: int, name: str) -> bool: ...

    # ── Channel Requests ─────────────────────────────────────────────

    @abstractmethod
    def request_channel(self, child_id: int, channel_id: str, channel_name: str) -> str: ...

    @abstractmethod
    def get_channel_request_status(
        self, child_id: int, channel_id: str
    ) -> Optional[str]: ...

    @abstractmethod
    def update_channel_request_status(
        self, child_id: int, channel_id: str, status: str
    ) -> bool: ...

    @abstractmethod
    def get_pending_channel_request(
        self, child_id: int, channel_id: str
    ) -> Optional[dict]: ...

    @abstractmethod
    def get_blocked_channels_set(self, child_id: int) -> set[str]: ...

    @abstractmethod
    def get_channels_due_for_refresh(
        self, child_id: int, interval_hours: int = 6
    ) -> list[dict]: ...

    @abstractmethod
    def get_child_ids_for_channel(self, channel_name: str) -> list[int]: ...

    @abstractmethod
    def get_all_channels_due_for_refresh(self, interval_hours: int = 6) -> list[dict]: ...

    @abstractmethod
    def update_channel_refreshed_at(self, child_id: int, channel_name: str) -> None: ...

    @abstractmethod
    def update_all_channels_refreshed_at(self, channel_name: str) -> None: ...

    # ── Word Filters ─────────────────────────────────────────────────

    @abstractmethod
    def add_word_filter(self, word: str) -> bool: ...

    @abstractmethod
    def remove_word_filter(self, word: str) -> bool: ...

    @abstractmethod
    def get_word_filters(self) -> list[str]: ...

    @abstractmethod
    def get_word_filters_set(self) -> set[str]: ...

    # ── Settings ─────────────────────────────────────────────────────

    @abstractmethod
    def get_setting(self, key: str, default: str = "") -> str: ...

    @abstractmethod
    def set_setting(self, key: str, value: str) -> None: ...

    # ── Search Logging ────────────────────────────────────────────────

    @abstractmethod
    def record_search(self, query: str, child_id: int, result_count: int) -> None: ...

    # ── Stats ─────────────────────────────────────────────────────────

    @abstractmethod
    def get_stats(self, child_id: Optional[int] = None) -> dict: ...

    # ── Pairing ───────────────────────────────────────────────────────

    @abstractmethod
    def create_pairing_session(
        self,
        device_name: Optional[str] = None,
        expiry_minutes: int = 5,
    ) -> dict: ...

    @abstractmethod
    def get_pairing_session(self, token: str) -> Optional[dict]: ...

    @abstractmethod
    def get_pairing_session_by_pin(self, pin: str) -> Optional[dict]: ...

    @abstractmethod
    def confirm_pairing(
        self, token: str, device_name: Optional[str] = None
    ) -> Optional[dict]: ...

    @abstractmethod
    def deny_pairing(self, token: str) -> bool: ...

    @abstractmethod
    def set_pairing_device_key(self, token: str, api_key: str) -> None: ...

    @abstractmethod
    def set_pairing_message_ids(
        self, token: str, chat_id: int, message_id: int
    ) -> None: ...

    @abstractmethod
    def get_paired_devices(self) -> list[dict]: ...

    @abstractmethod
    def revoke_device(self, device_id: int) -> bool: ...

    @abstractmethod
    def rename_device(self, device_id: int, name: str) -> bool: ...

    @abstractmethod
    def get_device_by_api_key(self, api_key: str) -> Optional[dict]: ...

    @abstractmethod
    def update_device_last_seen(self, device_id: int) -> None: ...

    @abstractmethod
    def cleanup_expired_pairing_sessions(self) -> int: ...

    @abstractmethod
    def close(self) -> None: ...
