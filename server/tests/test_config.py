"""Tests for config.py — configuration loading."""

import os
import tempfile
import pytest
import yaml

# Ensure server/ is importable
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import Config, load_config, expand_env_vars


class TestExpandEnvVars:
    def test_expands_dollar_brace(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "hello")
        assert expand_env_vars("${TEST_VAR}") == "hello"

    def test_expands_dollar_prefix(self, monkeypatch):
        monkeypatch.setenv("FOO", "bar")
        assert expand_env_vars("$FOO") == "bar"

    def test_expands_in_dict(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "localhost")
        result = expand_env_vars({"host": "${DB_HOST}", "port": 5432})
        assert result == {"host": "localhost", "port": 5432}

    def test_expands_in_list(self, monkeypatch):
        monkeypatch.setenv("ITEM", "x")
        assert expand_env_vars(["${ITEM}", "y"]) == ["x", "y"]

    def test_missing_var_becomes_empty(self):
        assert expand_env_vars("${NONEXISTENT_VAR_XYZ}") == ""

    def test_non_string_passthrough(self):
        assert expand_env_vars(42) == 42
        assert expand_env_vars(None) is None
        assert expand_env_vars(True) is True


class TestConfigFromEnv:
    def test_defaults(self, monkeypatch):
        for var in list(os.environ):
            if var.startswith("BRG_"):
                monkeypatch.delenv(var)
        cfg = Config.from_env()
        assert cfg.app_name == "KidsTube"
        assert cfg.web.host == "0.0.0.0"
        assert cfg.web.port == 8080
        assert cfg.invidious.base_url == "http://invidious:3000"
        assert cfg.watch_limits.daily_limit_minutes == 120
        assert cfg.watch_limits.timezone == "America/New_York"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("BRG_APP_NAME", "TestApp")
        monkeypatch.setenv("BRG_WEB_PORT", "9090")
        monkeypatch.setenv("BRG_INVIDIOUS_URL", "http://localhost:3000")
        monkeypatch.setenv("BRG_DAILY_LIMIT_MINUTES", "60")
        monkeypatch.setenv("BRG_API_KEY", "secret123")

        cfg = Config.from_env()
        assert cfg.app_name == "TestApp"
        assert cfg.web.port == 9090
        assert cfg.invidious.base_url == "http://localhost:3000"
        assert cfg.watch_limits.daily_limit_minutes == 60
        assert cfg.api_key == "secret123"


class TestConfigFromYaml:
    def test_loads_yaml(self, tmp_path):
        config_data = {
            "app_name": "YAMLApp",
            "web": {"port": 7070},
            "telegram": {"bot_token": "test-token"},
            "invidious": {"base_url": "http://inv:3000"},
            "database": {"path": "test.db"},
            "watch_limits": {"daily_limit_minutes": 90},
            "api_key": "yaml-key",
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = Config.from_yaml(config_file)
        assert cfg.app_name == "YAMLApp"
        assert cfg.web.port == 7070
        assert cfg.telegram.bot_token == "test-token"
        assert cfg.api_key == "yaml-key"

    def test_yaml_with_env_expansion(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "expanded-token")
        config_data = {
            "telegram": {"bot_token": "${MY_TOKEN}"},
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = Config.from_yaml(config_file)
        assert cfg.telegram.bot_token == "expanded-token"


class TestLoadConfig:
    def test_fallback_to_env(self):
        cfg = load_config()
        assert isinstance(cfg, Config)

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")

    def test_invalid_timezone_falls_back(self, monkeypatch):
        monkeypatch.setenv("BRG_TIMEZONE", "Invalid/Timezone")
        cfg = load_config()
        assert cfg.watch_limits.timezone == ""
