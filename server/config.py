"""Configuration management for the server.

Loads from environment variables (primary) or YAML config file (optional).
Supports ${VAR} expansion in YAML values.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def expand_env_vars(value: Any) -> Any:
    """Recursively expand environment variables in strings, dicts, and lists.

    Supports both ${VAR} and $VAR patterns.
    """
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([^}]+)\}")
        result = pattern.sub(lambda m: os.environ.get(m.group(1), ""), value)
        pattern = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
        result = pattern.sub(lambda m: os.environ.get(m.group(1), ""), result)
        return result
    elif isinstance(value, dict):
        return {k: expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [expand_env_vars(item) for item in value]
    else:
        return value


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    poll_interval: int = 3000
    base_url: str = ""  # External base URL (e.g. https://kidstube.scavone.net)


@dataclass
class TelegramConfig:
    bot_token: str = ""
    admin_chat_id: str = ""


@dataclass
class InvidiousConfig:
    base_url: str = "http://invidious:3000"
    search_max_results: int = 20
    channel_cache_ttl: int = 1800
    channel_refresh_hours: int = 6


@dataclass
class DatabaseConfig:
    path: str = "db/videos.db"


@dataclass
class WatchLimitsConfig:
    daily_limit_minutes: int = 120
    timezone: str = "America/New_York"
    notify_on_limit: bool = True


@dataclass
class Config:
    app_name: str = "KidsTube"
    web: WebConfig = field(default_factory=WebConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    invidious: InvidiousConfig = field(default_factory=InvidiousConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    watch_limits: WatchLimitsConfig = field(default_factory=WatchLimitsConfig)
    api_key: str = ""
    preferred_audio_lang: str = ""

    @classmethod
    def from_yaml(cls, path: Path | str) -> "Config":
        path = Path(path)
        with open(path, "r") as f:
            raw_config = yaml.safe_load(f)

        expanded = expand_env_vars(raw_config)

        return cls(
            app_name=expanded.get("app_name", "KidsTube"),
            web=WebConfig(**expanded.get("web", {})),
            telegram=TelegramConfig(**expanded.get("telegram", {})),
            invidious=InvidiousConfig(**expanded.get("invidious", {})),
            database=DatabaseConfig(**expanded.get("database", {})),
            watch_limits=WatchLimitsConfig(**expanded.get("watch_limits", {})),
            api_key=expanded.get("api_key", ""),
            preferred_audio_lang=expanded.get("preferred_audio_lang", ""),
        )

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            app_name=os.environ.get("BRG_APP_NAME", "KidsTube"),
            web=WebConfig(
                host=os.environ.get("BRG_WEB_HOST", "0.0.0.0"),
                port=int(os.environ.get("BRG_WEB_PORT", "8080")),
                poll_interval=int(os.environ.get("BRG_POLL_INTERVAL", "3000")),
                base_url=os.environ.get("BRG_BASE_URL", ""),
            ),
            telegram=TelegramConfig(
                bot_token=os.environ.get("BRG_BOT_TOKEN", ""),
                admin_chat_id=os.environ.get("BRG_ADMIN_CHAT_ID", ""),
            ),
            invidious=InvidiousConfig(
                base_url=os.environ.get("BRG_INVIDIOUS_URL", "http://invidious:3000"),
                search_max_results=int(os.environ.get("BRG_SEARCH_MAX_RESULTS", "20")),
                channel_cache_ttl=int(os.environ.get("BRG_CHANNEL_CACHE_TTL", "1800")),
                channel_refresh_hours=int(os.environ.get("BRG_CHANNEL_REFRESH_HOURS", "6")),
            ),
            database=DatabaseConfig(
                path=os.environ.get("BRG_DB_PATH", "db/videos.db"),
            ),
            watch_limits=WatchLimitsConfig(
                daily_limit_minutes=int(os.environ.get("BRG_DAILY_LIMIT_MINUTES", "120")),
                timezone=os.environ.get("BRG_TIMEZONE", "America/New_York"),
                notify_on_limit=os.environ.get("BRG_NOTIFY_ON_LIMIT", "true").lower() == "true",
            ),
            api_key=os.environ.get("BRG_API_KEY", ""),
            preferred_audio_lang=os.environ.get("BRG_PREFERRED_AUDIO_LANG", ""),
        )


def load_config(config_path: str | None = None) -> Config:
    """Load configuration from file or environment.

    Tries in order:
    1. Provided config_path
    2. Default paths: config.yaml, config.yml
    3. Environment variables (fallback)
    """
    config: Config | None = None

    if config_path:
        path = Path(config_path)
        if path.exists():
            config = Config.from_yaml(path)
        else:
            raise FileNotFoundError(f"Config file not found: {config_path}")
    else:
        for default_path in ["config.yaml", "config.yml"]:
            path = Path(default_path)
            if path.exists():
                config = Config.from_yaml(path)
                break

    if config is None:
        config = Config.from_env()

    # Validate admin_chat_id
    admin_id = config.telegram.admin_chat_id
    if not admin_id:
        logger.warning("telegram.admin_chat_id is empty — bot commands will be unauthorized")
    elif not admin_id.lstrip("-").isdigit():
        logger.warning("telegram.admin_chat_id %r is not numeric — admin checks will fail", admin_id)

    # Validate timezone
    tz = config.watch_limits.timezone
    if tz:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(tz)
        except Exception:
            logger.warning("Invalid timezone %r in config, falling back to UTC", tz)
            config.watch_limits.timezone = ""

    return config
