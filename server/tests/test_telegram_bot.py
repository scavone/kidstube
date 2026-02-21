"""Tests for bot/telegram_bot.py — Telegram bot with multi-child support.

Uses unittest.mock to simulate Telegram API calls without a real bot token.
Tests cover: admin auth, child resolution, notification flow, all commands,
callback handling, and multi-child behavior.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from config import Config
from data.video_store import VideoStore
from bot.telegram_bot import TelegramBot, _esc, _progress_bar, format_duration


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def cfg():
    return Config(
        app_name="TestApp",
        api_key="test-key",
        watch_limits=Config.__dataclass_fields__["watch_limits"].default_factory(),
    )


@pytest.fixture
def store(tmp_path):
    s = VideoStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def bot(cfg, store):
    """Create a bot without starting it (no polling)."""
    b = TelegramBot(
        bot_token="fake-token",
        admin_chat_id="12345",
        video_store=store,
        config=cfg,
    )
    return b


@pytest.fixture
def admin_update():
    """Create a mock Telegram Update from the admin user."""
    update = MagicMock()
    update.effective_chat.id = 12345
    update.effective_user.id = 12345
    update.effective_message = AsyncMock()
    update.effective_message.reply_text = AsyncMock()
    update.effective_message.text = "/test"
    update.effective_message.caption = None
    return update


@pytest.fixture
def non_admin_update():
    """Create a mock Telegram Update from a non-admin user."""
    update = MagicMock()
    update.effective_chat.id = 99999
    update.effective_user.id = 99999
    update.effective_message = AsyncMock()
    update.effective_message.reply_text = AsyncMock()
    return update


@pytest.fixture
def context():
    """Create a mock ContextTypes.DEFAULT_TYPE."""
    ctx = MagicMock()
    ctx.args = []
    return ctx


# ── Helper Tests ──────────────────────────────────────────────────

class TestHelpers:
    def test_esc_html(self):
        assert _esc("Hello & <World>") == "Hello &amp; &lt;World&gt;"
        assert _esc("Normal text") == "Normal text"
        assert _esc("") == ""

    def test_progress_bar(self):
        assert _progress_bar(0.0) == "[----------]"
        assert _progress_bar(1.0) == "[==========]"
        assert _progress_bar(0.5) == "[=====----- ]" or len(_progress_bar(0.5)) == 12
        # Clamps to bounds
        assert _progress_bar(1.5) == "[==========]"
        assert _progress_bar(-0.5) == "[----------]"

    def test_format_duration(self):
        assert format_duration(0) == "0:00"
        assert format_duration(120) == "2:00"
        assert format_duration(3661) == "1:01:01"
        assert format_duration(None) == "?"
        assert format_duration(-1) == "?"
        assert format_duration(59) == "0:59"
        assert format_duration(3600) == "1:00:00"


# ── Admin Auth ────────────────────────────────────────────────────

class TestAdminAuth:
    def test_is_admin_by_chat_id(self, bot):
        update = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user.id = 0
        assert bot._is_admin(update) is True

    def test_is_admin_by_user_id(self, bot):
        update = MagicMock()
        update.effective_chat.id = 0
        update.effective_user.id = 12345
        assert bot._is_admin(update) is True

    def test_not_admin(self, bot):
        update = MagicMock()
        update.effective_chat.id = 99999
        update.effective_user.id = 99999
        assert bot._is_admin(update) is False

    def test_no_admin_configured(self, store, cfg):
        bot = TelegramBot("token", "", store, cfg)
        update = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user.id = 12345
        assert bot._is_admin(update) is False

    @pytest.mark.asyncio
    async def test_check_admin_rejects(self, bot, non_admin_update):
        result = await bot._check_admin(non_admin_update)
        assert result is False
        non_admin_update.effective_message.reply_text.assert_called_once_with("Unauthorized.")

    @pytest.mark.asyncio
    async def test_check_admin_accepts(self, bot, admin_update):
        result = await bot._check_admin(admin_update)
        assert result is True


# ── Child Resolution ──────────────────────────────────────────────

class TestChildResolution:
    def test_resolve_by_name(self, bot, store):
        store.add_child("Alex")
        child = bot._resolve_child("Alex")
        assert child is not None
        assert child["name"] == "Alex"

    def test_resolve_case_insensitive(self, bot, store):
        store.add_child("Alex")
        child = bot._resolve_child("alex")
        assert child is not None

    def test_resolve_default_single_child(self, bot, store):
        store.add_child("Alex")
        child = bot._resolve_child()
        assert child is not None
        assert child["name"] == "Alex"

    def test_resolve_none_multiple_children(self, bot, store):
        store.add_child("Alex")
        store.add_child("Sam")
        child = bot._resolve_child()
        assert child is None

    def test_resolve_not_found(self, bot, store):
        store.add_child("Alex")
        child = bot._resolve_child("Nonexistent")
        assert child is None

    def test_parse_child_args_with_child_name(self, bot, store):
        store.add_child("Alex")
        child, remaining = bot._parse_child_args(["Alex", "set", "90"])
        assert child is not None
        assert child["name"] == "Alex"
        assert remaining == ["set", "90"]

    def test_parse_child_args_no_child_single(self, bot, store):
        store.add_child("Alex")
        child, remaining = bot._parse_child_args(["set", "90"])
        assert child is not None
        assert child["name"] == "Alex"
        assert remaining == ["set", "90"]

    def test_parse_child_args_empty(self, bot, store):
        child, remaining = bot._parse_child_args([])
        assert child is None
        assert remaining == []


# ── /help Command ─────────────────────────────────────────────────

class TestHelpCommand:
    @pytest.mark.asyncio
    async def test_help_shows_commands(self, bot, admin_update, context):
        await bot._cmd_help(admin_update, context)
        admin_update.effective_message.reply_text.assert_called_once()
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "TestApp" in msg
        assert "/kids" in msg
        assert "/pending" in msg
        assert "/time" in msg

    @pytest.mark.asyncio
    async def test_help_rejected_non_admin(self, bot, non_admin_update, context):
        await bot._cmd_help(non_admin_update, context)
        non_admin_update.effective_message.reply_text.assert_called_once_with("Unauthorized.")


# ── /kids Command ─────────────────────────────────────────────────

class TestKidsCommand:
    @pytest.mark.asyncio
    async def test_no_kids(self, bot, admin_update, context):
        await bot._cmd_kids(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "No child profiles" in msg

    @pytest.mark.asyncio
    async def test_kids_with_profiles(self, bot, admin_update, context, store):
        child = store.add_child("Alex", "👦")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")
        store.add_child("Sam", "👧")

        await bot._cmd_kids(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Alex" in msg
        assert "Sam" in msg
        assert "Child Profiles (2)" in msg

    @pytest.mark.asyncio
    async def test_kids_shows_pending_count(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Title", "Channel")
        store.request_video(child["id"], "vid1")

        await bot._cmd_kids(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Pending: 1" in msg


# ── /addkid Command ───────────────────────────────────────────────

class TestAddKidCommand:
    @pytest.mark.asyncio
    async def test_addkid_no_args(self, bot, admin_update, context):
        context.args = []
        await bot._cmd_addkid(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Usage:" in msg

    @pytest.mark.asyncio
    async def test_addkid_success(self, bot, admin_update, context, store):
        context.args = ["Alex"]
        await bot._cmd_addkid(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Alex" in msg
        assert "profile created" in msg
        assert store.get_child_by_name("Alex") is not None

    @pytest.mark.asyncio
    async def test_addkid_with_avatar(self, bot, admin_update, context, store):
        context.args = ["Sam", "👧"]
        await bot._cmd_addkid(admin_update, context)
        child = store.get_child_by_name("Sam")
        assert child["avatar"] == "👧"

    @pytest.mark.asyncio
    async def test_addkid_duplicate(self, bot, admin_update, context, store):
        store.add_child("Alex")
        context.args = ["Alex"]
        await bot._cmd_addkid(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "already exists" in msg

    @pytest.mark.asyncio
    async def test_addkid_sets_default_limit(self, bot, admin_update, context, store, cfg):
        context.args = ["Alex"]
        await bot._cmd_addkid(admin_update, context)
        child = store.get_child_by_name("Alex")
        limit = store.get_child_setting(child["id"], "daily_limit_minutes")
        assert limit == str(cfg.watch_limits.daily_limit_minutes)


# ── /stats Command ────────────────────────────────────────────────

class TestStatsCommand:
    @pytest.mark.asyncio
    async def test_stats_overall(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_video("v1", "T1", "Ch")
        store.request_video(child["id"], "v1")

        context.args = []
        await bot._cmd_stats(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Overall Stats" in msg
        assert "Pending: 1" in msg

    @pytest.mark.asyncio
    async def test_stats_per_child(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_video("v1", "T1", "Ch")
        store.request_video(child["id"], "v1")
        store.update_video_status(child["id"], "v1", "approved")

        context.args = ["Alex"]
        await bot._cmd_stats(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Alex" in msg
        assert "Approved: 1" in msg

    @pytest.mark.asyncio
    async def test_stats_child_not_found(self, bot, admin_update, context):
        context.args = ["Ghost"]
        await bot._cmd_stats(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "not found" in msg


# ── /pending Command ──────────────────────────────────────────────

class TestPendingCommand:
    @pytest.mark.asyncio
    async def test_pending_empty(self, bot, admin_update, context):
        await bot._cmd_pending(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "No pending" in msg

    @pytest.mark.asyncio
    async def test_pending_with_items(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_video("vid1", "Test Video", "Test Channel")
        store.request_video(child["id"], "vid1")

        await bot._cmd_pending(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Pending Requests" in msg
        assert "Alex" in msg
        assert "Test Video" in msg


# ── /approved Command ─────────────────────────────────────────────

class TestApprovedCommand:
    @pytest.mark.asyncio
    async def test_approved_empty(self, bot, admin_update, context, store):
        store.add_child("Alex")
        context.args = ["Alex"]
        await bot._cmd_approved(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "No approved" in msg

    @pytest.mark.asyncio
    async def test_approved_with_videos(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_video("v1", "Approved Video", "Channel")
        store.request_video(child["id"], "v1")
        store.update_video_status(child["id"], "v1", "approved")

        context.args = ["Alex"]
        await bot._cmd_approved(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Approved for Alex" in msg
        assert "Approved Video" in msg

    @pytest.mark.asyncio
    async def test_approved_multiple_children_no_name(self, bot, admin_update, context, store):
        store.add_child("Alex")
        store.add_child("Sam")
        context.args = []
        await bot._cmd_approved(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Specify a name" in msg or "Multiple children" in msg

    @pytest.mark.asyncio
    async def test_approved_single_child_default(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_video("v1", "Title", "Ch")
        store.request_video(child["id"], "v1")
        store.update_video_status(child["id"], "v1", "approved")

        context.args = []
        await bot._cmd_approved(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Alex" in msg


# ── /channel Command ──────────────────────────────────────────────

class TestChannelCommand:
    @pytest.mark.asyncio
    async def test_channel_list_empty(self, bot, admin_update, context):
        context.args = []
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "No channels" in msg

    @pytest.mark.asyncio
    async def test_channel_allow(self, bot, admin_update, context, store):
        context.args = ["allow", "GoodChannel", "edu"]
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "allow list" in msg
        assert store.is_channel_allowed("GoodChannel")

    @pytest.mark.asyncio
    async def test_channel_block(self, bot, admin_update, context, store):
        context.args = ["block", "BadChannel"]
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "block list" in msg
        assert store.is_channel_blocked("BadChannel")

    @pytest.mark.asyncio
    async def test_channel_unallow(self, bot, admin_update, context, store):
        store.add_channel("TestCh", "allowed")
        context.args = ["unallow", "TestCh"]
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "removed" in msg
        assert not store.is_channel_allowed("TestCh")

    @pytest.mark.asyncio
    async def test_channel_unblock(self, bot, admin_update, context, store):
        store.add_channel("BadCh", "blocked")
        context.args = ["unblock", "BadCh"]
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "removed" in msg

    @pytest.mark.asyncio
    async def test_channel_list_with_channels(self, bot, admin_update, context, store):
        store.add_channel("Allowed1", "allowed")
        store.add_channel("Blocked1", "blocked")
        context.args = []
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Allowed Channels" in msg
        assert "Blocked Channels" in msg

    @pytest.mark.asyncio
    async def test_channel_invalid_subcmd(self, bot, admin_update, context):
        context.args = ["invalid"]
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Usage:" in msg


# ── /time Command ─────────────────────────────────────────────────

class TestTimeCommand:
    @pytest.mark.asyncio
    async def test_time_status_single_child(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "90")
        context.args = []
        await bot._cmd_time(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Alex" in msg
        assert "90 min" in msg

    @pytest.mark.asyncio
    async def test_time_set(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        context.args = ["Alex", "set", "45"]
        await bot._cmd_time(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "45" in msg
        assert store.get_child_setting(child["id"], "daily_limit_minutes") == "45"

    @pytest.mark.asyncio
    async def test_time_set_single_child(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        context.args = ["set", "60"]
        await bot._cmd_time(admin_update, context)
        assert store.get_child_setting(child["id"], "daily_limit_minutes") == "60"

    @pytest.mark.asyncio
    async def test_time_off(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        context.args = ["Alex", "off"]
        await bot._cmd_time(admin_update, context)
        assert store.get_child_setting(child["id"], "daily_limit_minutes") == "0"

    @pytest.mark.asyncio
    async def test_time_schedule(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        context.args = ["Alex", "schedule", "800", "2000"]
        await bot._cmd_time(admin_update, context)
        assert store.get_child_setting(child["id"], "schedule_start") == "08:00"
        assert store.get_child_setting(child["id"], "schedule_end") == "20:00"

    @pytest.mark.asyncio
    async def test_time_schedule_off(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "schedule_start", "08:00")
        store.set_child_setting(child["id"], "schedule_end", "20:00")
        context.args = ["Alex", "schedule", "off", "off"]
        await bot._cmd_time(admin_update, context)
        assert store.get_child_setting(child["id"], "schedule_start") == ""

    @pytest.mark.asyncio
    async def test_time_shorthand_minutes(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        context.args = ["Alex", "120"]
        await bot._cmd_time(admin_update, context)
        assert store.get_child_setting(child["id"], "daily_limit_minutes") == "120"

    @pytest.mark.asyncio
    async def test_time_no_children(self, bot, admin_update, context):
        context.args = []
        await bot._cmd_time(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "No child profiles" in msg

    @pytest.mark.asyncio
    async def test_time_multiple_children_no_name(self, bot, admin_update, context, store):
        store.add_child("Alex")
        store.add_child("Sam")
        context.args = ["set", "60"]
        await bot._cmd_time(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Specify" in msg or "Multiple" in msg

    @pytest.mark.asyncio
    async def test_time_invalid_minutes(self, bot, admin_update, context, store):
        store.add_child("Alex")
        context.args = ["Alex", "set", "abc"]
        await bot._cmd_time(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Invalid" in msg


# ── /watch Command ────────────────────────────────────────────────

class TestWatchCommand:
    @pytest.mark.asyncio
    async def test_watch_no_activity(self, bot, admin_update, context, store):
        store.add_child("Alex")
        context.args = ["Alex"]
        await bot._cmd_watch(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "No watch activity" in msg

    @pytest.mark.asyncio
    async def test_watch_with_activity(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_video("v1", "Fun Video", "Channel")
        store.record_watch_seconds("v1", child["id"], 300)

        context.args = ["Alex"]
        await bot._cmd_watch(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Watch Activity" in msg
        assert "Fun Video" in msg

    @pytest.mark.asyncio
    async def test_watch_single_child_default(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_video("v1", "Video", "Ch")
        store.record_watch_seconds("v1", child["id"], 60)

        context.args = []
        await bot._cmd_watch(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Alex" in msg


# ── /search Command ───────────────────────────────────────────────

class TestSearchCommand:
    @pytest.mark.asyncio
    async def test_search_list_empty(self, bot, admin_update, context):
        context.args = []
        await bot._cmd_search(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "No word filters" in msg

    @pytest.mark.asyncio
    async def test_search_add_filter(self, bot, admin_update, context, store):
        context.args = ["add", "badword"]
        await bot._cmd_search(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "added" in msg
        assert "badword" in store.get_word_filters()

    @pytest.mark.asyncio
    async def test_search_remove_filter(self, bot, admin_update, context, store):
        store.add_word_filter("testword")
        context.args = ["remove", "testword"]
        await bot._cmd_search(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "removed" in msg

    @pytest.mark.asyncio
    async def test_search_add_duplicate(self, bot, admin_update, context, store):
        store.add_word_filter("badword")
        context.args = ["add", "badword"]
        await bot._cmd_search(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "already exists" in msg

    @pytest.mark.asyncio
    async def test_search_list_filters(self, bot, admin_update, context, store):
        store.add_word_filter("word1")
        store.add_word_filter("word2")
        context.args = []
        await bot._cmd_search(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Word Filters (2)" in msg
        assert "word1" in msg
        assert "word2" in msg


# ── Notification ──────────────────────────────────────────────────

class TestNotification:
    @pytest.mark.asyncio
    async def test_notify_sends_message(self, bot, store):
        """Test that notify_new_request sends a message to admin."""
        child = store.add_child("Alex")
        video = {
            "video_id": "abc12345678",
            "title": "Test Video",
            "channel_name": "Test Channel",
            "duration": 300,
            "thumbnail_url": "",
        }

        # Mock the bot application and its bot object
        bot._app = MagicMock()
        bot._app.bot = AsyncMock()
        bot._app.bot.send_message = AsyncMock()

        await bot.notify_new_request(child, video)
        bot._app.bot.send_message.assert_called_once()

        call_kwargs = bot._app.bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == 12345
        assert "[Alex]" in call_kwargs["text"]
        assert "Test Video" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_notify_includes_keyboard(self, bot, store):
        """Test that notification includes inline buttons."""
        child = store.add_child("Alex")
        video = {
            "video_id": "abc12345678",
            "title": "Test Video",
            "channel_name": "Channel",
            "thumbnail_url": "",
        }

        bot._app = MagicMock()
        bot._app.bot = AsyncMock()
        bot._app.bot.send_message = AsyncMock()

        await bot.notify_new_request(child, video)

        call_kwargs = bot._app.bot.send_message.call_args[1]
        keyboard = call_kwargs["reply_markup"]
        assert keyboard is not None
        # Flatten all buttons
        all_buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_datas = [b.callback_data for b in all_buttons if b.callback_data]
        assert any("approve_edu" in d for d in callback_datas)
        assert any("deny" in d for d in callback_datas)
        # Verify child_id is embedded
        assert any(f":{child['id']}:" in d for d in callback_datas)

    @pytest.mark.asyncio
    async def test_notify_with_thumbnail(self, bot, store):
        """Test that thumbnail is fetched and sent as photo."""
        child = store.add_child("Alex")
        video = {
            "video_id": "abc12345678",
            "title": "Test Video",
            "channel_name": "Channel",
            "thumbnail_url": "https://i.ytimg.com/vi/abc/mqdefault.jpg",
        }

        bot._app = MagicMock()
        bot._app.bot = AsyncMock()
        bot._app.bot.send_photo = AsyncMock()
        bot._app.bot.send_message = AsyncMock()

        # Mock httpx to return a successful image
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNG fake image data"

        with patch("bot.telegram_bot.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await bot.notify_new_request(child, video)

        bot._app.bot.send_photo.assert_called_once()
        bot._app.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_no_app(self, bot, store):
        """If bot app is not initialized, notify is a no-op."""
        child = store.add_child("Alex")
        video = {"video_id": "test", "title": "T"}
        bot._app = None
        # Should not raise
        await bot.notify_new_request(child, video)

    @pytest.mark.asyncio
    async def test_notify_no_admin(self, store, cfg):
        """If no admin chat id, notify is a no-op."""
        bot = TelegramBot("token", "", store, cfg)
        child = store.add_child("Alex")
        video = {"video_id": "test", "title": "T"}
        bot._app = MagicMock()
        # Should not raise
        await bot.notify_new_request(child, video)


# ── Callback Handling ─────────────────────────────────────────────

class TestCallbackHandling:
    def _make_callback_update(self, data: str, admin=True):
        """Create a mock Update with callback_query."""
        update = MagicMock()
        chat_id = 12345 if admin else 99999
        update.effective_chat.id = chat_id
        update.effective_user.id = chat_id
        update.callback_query = AsyncMock()
        update.callback_query.data = data
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_caption = AsyncMock()
        update.callback_query.message = AsyncMock()
        return update

    @pytest.mark.asyncio
    async def test_approve_edu(self, bot, store, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "Channel")
        store.request_video(child["id"], "vid12345678")

        update = self._make_callback_update(f"approve_edu:{child['id']}:vid12345678")
        await bot._handle_callback(update, context)

        assert store.get_video_status(child["id"], "vid12345678") == "approved"
        update.callback_query.edit_message_caption.assert_called_once()
        caption = update.callback_query.edit_message_caption.call_args[1]["caption"]
        assert "Approved (Educational)" in caption
        assert "Alex" in caption

    @pytest.mark.asyncio
    async def test_approve_fun(self, bot, store, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "Channel")
        store.request_video(child["id"], "vid12345678")

        update = self._make_callback_update(f"approve_fun:{child['id']}:vid12345678")
        await bot._handle_callback(update, context)

        assert store.get_video_status(child["id"], "vid12345678") == "approved"
        caption = update.callback_query.edit_message_caption.call_args[1]["caption"]
        assert "Entertainment" in caption

    @pytest.mark.asyncio
    async def test_deny(self, bot, store, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "Channel")
        store.request_video(child["id"], "vid12345678")

        update = self._make_callback_update(f"deny:{child['id']}:vid12345678")
        await bot._handle_callback(update, context)

        assert store.get_video_status(child["id"], "vid12345678") == "denied"
        caption = update.callback_query.edit_message_caption.call_args[1]["caption"]
        assert "Denied" in caption

    @pytest.mark.asyncio
    async def test_revoke(self, bot, store, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "Channel")
        store.request_video(child["id"], "vid12345678")
        store.update_video_status(child["id"], "vid12345678", "approved")

        update = self._make_callback_update(f"revoke:{child['id']}:vid12345678")
        await bot._handle_callback(update, context)

        assert store.get_video_status(child["id"], "vid12345678") == "denied"
        caption = update.callback_query.edit_message_caption.call_args[1]["caption"]
        assert "Revoked" in caption

    @pytest.mark.asyncio
    async def test_allowchan_edu(self, bot, store, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "GoodChannel")
        store.request_video(child["id"], "vid12345678")

        update = self._make_callback_update(f"allowchan_edu:{child['id']}:vid12345678")
        await bot._handle_callback(update, context)

        assert store.is_channel_allowed("GoodChannel")
        assert store.get_video_status(child["id"], "vid12345678") == "approved"

    @pytest.mark.asyncio
    async def test_blockchan(self, bot, store, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "BadChannel")
        store.request_video(child["id"], "vid12345678")

        update = self._make_callback_update(f"blockchan:{child['id']}:vid12345678")
        await bot._handle_callback(update, context)

        assert store.is_channel_blocked("BadChannel")
        assert store.get_video_status(child["id"], "vid12345678") == "denied"

    @pytest.mark.asyncio
    async def test_callback_non_admin_rejected(self, bot, store, context):
        update = self._make_callback_update("approve_edu:1:vid123", admin=False)
        await bot._handle_callback(update, context)
        update.callback_query.answer.assert_called_once_with("Unauthorized")

    @pytest.mark.asyncio
    async def test_callback_empty_data(self, bot, context):
        update = MagicMock()
        update.callback_query = AsyncMock()
        update.callback_query.data = ""
        await bot._handle_callback(update, context)


# ── Multi-Child Approval Flow ─────────────────────────────────────

class TestMultiChildApproval:
    @pytest.mark.asyncio
    async def test_approve_for_one_child_not_other(self, bot, store, context):
        """Approving a video for Alex should not affect Sam."""
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.add_video("vid12345678", "Shared Video", "Channel")
        store.request_video(alex["id"], "vid12345678")
        store.request_video(sam["id"], "vid12345678")

        update = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user.id = 12345
        update.callback_query = AsyncMock()
        update.callback_query.data = f"approve_edu:{alex['id']}:vid12345678"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_caption = AsyncMock()
        update.callback_query.message = AsyncMock()

        await bot._handle_callback(update, context)

        assert store.get_video_status(alex["id"], "vid12345678") == "approved"
        assert store.get_video_status(sam["id"], "vid12345678") == "pending"

    @pytest.mark.asyncio
    async def test_allowchan_approves_only_requesting_child(self, bot, store, context):
        """Allowing a channel auto-approves only the requesting child's video."""
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.add_video("vid12345678", "Video", "NewChannel")
        store.request_video(alex["id"], "vid12345678")
        store.request_video(sam["id"], "vid12345678")

        update = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user.id = 12345
        update.callback_query = AsyncMock()
        update.callback_query.data = f"allowchan_edu:{alex['id']}:vid12345678"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_caption = AsyncMock()
        update.callback_query.message = AsyncMock()

        await bot._handle_callback(update, context)

        assert store.is_channel_allowed("NewChannel")
        assert store.get_video_status(alex["id"], "vid12345678") == "approved"
        # Sam's request remains pending (channel allow only auto-approves future requests)
        assert store.get_video_status(sam["id"], "vid12345678") == "pending"

    @pytest.mark.asyncio
    async def test_notification_has_child_context(self, bot, store):
        """Notification callback_data embeds child_id for correct routing."""
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        video = {
            "video_id": "abc12345678",
            "title": "Video",
            "channel_name": "Channel",
            "thumbnail_url": "",
        }

        bot._app = MagicMock()
        bot._app.bot = AsyncMock()
        bot._app.bot.send_message = AsyncMock()

        # Notify for Alex
        await bot.notify_new_request(alex, video)
        call_kwargs = bot._app.bot.send_message.call_args[1]
        keyboard = call_kwargs["reply_markup"]
        first_approve = keyboard.inline_keyboard[1][0]
        assert f":{alex['id']}:" in first_approve.callback_data

        # Notify for Sam
        bot._app.bot.send_message.reset_mock()
        await bot.notify_new_request(sam, video)
        call_kwargs = bot._app.bot.send_message.call_args[1]
        keyboard = call_kwargs["reply_markup"]
        first_approve = keyboard.inline_keyboard[1][0]
        assert f":{sam['id']}:" in first_approve.callback_data


# ── Bot Lifecycle ─────────────────────────────────────────────────

class TestBotLifecycle:
    def test_bot_no_token(self, store, cfg):
        """Bot with empty token should be constructable."""
        bot = TelegramBot("", "12345", store, cfg)
        assert bot.bot_token == ""

    @pytest.mark.asyncio
    async def test_start_no_token_noop(self, store, cfg):
        """Starting a bot without a token should be a no-op."""
        bot = TelegramBot("", "12345", store, cfg)
        await bot.start()
        assert bot._app is None

    @pytest.mark.asyncio
    async def test_stop_without_start(self, bot):
        """Stopping a bot that was never started should be safe."""
        await bot.stop()

    def test_set_video_category(self, bot, store):
        """Test the helper that sets video category."""
        store.add_video("vid1", "Title", "Ch")
        bot._set_video_category("vid1", "edu")
        video = store.get_video("vid1")
        assert video["category"] == "edu"
