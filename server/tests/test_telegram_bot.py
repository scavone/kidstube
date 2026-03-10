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
    async def test_help_shows_commands(self, bot, admin_update, context, store):
        store.add_child("Alex")  # Need a child so help shows full command list
        await bot._cmd_help(admin_update, context)
        admin_update.effective_message.reply_text.assert_called_once()
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "TestApp" in msg
        assert "/child" in msg
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

    @pytest.mark.asyncio
    async def test_kids_shows_free_day(self, bot, admin_update, context, store):
        from utils import get_today_str
        child = store.add_child("Alex")
        tz = bot.config.watch_limits.timezone
        today = get_today_str(tz)
        store.set_child_setting(child["id"], "free_day_date", today)

        await bot._cmd_kids(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Free day" in msg
        assert "unlimited" in msg


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
        msg = admin_update.effective_message.reply_text.call_args_list[0][0][0]
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


# ── /editkid Command ─────────────────────────────────────────────

class TestEditKidCommand:
    @pytest.mark.asyncio
    async def test_editkid_no_args(self, bot, admin_update, context):
        context.args = []
        await bot._cmd_editkid(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Usage:" in msg

    @pytest.mark.asyncio
    async def test_editkid_rename(self, bot, admin_update, context, store):
        store.add_child("Alex")
        context.args = ["Alex", "Alexander"]
        await bot._cmd_editkid(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Alexander" in msg
        assert store.get_child_by_name("Alexander") is not None

    @pytest.mark.asyncio
    async def test_editkid_rename_with_avatar(self, bot, admin_update, context, store):
        store.add_child("Alex", "👦")
        context.args = ["Alex", "Sam", "👧"]
        await bot._cmd_editkid(admin_update, context)
        child = store.get_child_by_name("Sam")
        assert child is not None
        assert child["avatar"] == "👧"

    @pytest.mark.asyncio
    async def test_editkid_avatar_only(self, bot, admin_update, context, store):
        store.add_child("Alex", "👦")
        context.args = ["Alex", "avatar", "👧"]
        await bot._cmd_editkid(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "👧" in msg
        child = store.get_child_by_name("Alex")
        assert child["avatar"] == "👧"

    @pytest.mark.asyncio
    async def test_editkid_not_found(self, bot, admin_update, context):
        context.args = ["Ghost", "NewName"]
        await bot._cmd_editkid(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "not found" in msg

    @pytest.mark.asyncio
    async def test_editkid_name_conflict(self, bot, admin_update, context, store):
        store.add_child("Alex")
        store.add_child("Sam")
        context.args = ["Sam", "Alex"]
        await bot._cmd_editkid(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Failed" in msg or "already exist" in msg

    @pytest.mark.asyncio
    async def test_editkid_one_arg_shows_usage(self, bot, admin_update, context, store):
        store.add_child("Alex")
        context.args = ["Alex"]
        await bot._cmd_editkid(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Usage:" in msg


# ── /removekid Command ───────────────────────────────────────────

class TestRemoveKidCommand:
    @pytest.mark.asyncio
    async def test_removekid_no_args(self, bot, admin_update, context):
        context.args = []
        await bot._cmd_removekid(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Usage:" in msg

    @pytest.mark.asyncio
    async def test_removekid_success(self, bot, admin_update, context, store):
        child = store.add_child("Alex", "👦")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")
        context.args = ["Alex"]
        await bot._cmd_removekid(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Alex" in msg
        assert "removed" in msg
        assert store.get_child_by_name("Alex") is None

    @pytest.mark.asyncio
    async def test_removekid_not_found(self, bot, admin_update, context):
        context.args = ["Ghost"]
        await bot._cmd_removekid(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "not found" in msg

    @pytest.mark.asyncio
    async def test_removekid_non_admin(self, bot, non_admin_update, context, store):
        store.add_child("Alex")
        context.args = ["Alex"]
        await bot._cmd_removekid(non_admin_update, context)
        non_admin_update.effective_message.reply_text.assert_called_once_with("Unauthorized.")
        assert store.get_child_by_name("Alex") is not None


# ── Photo Avatar Handler ─────────────────────────────────────────

class TestPhotoHandler:
    @pytest.mark.asyncio
    async def test_photo_avatar_upload(self, bot, store):
        """Test setting a photo avatar via message with photo."""
        child = store.add_child("Alex")

        update = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user.id = 12345
        update.effective_message = MagicMock()
        update.effective_message.caption = "avatar Alex"
        update.effective_message.reply_text = AsyncMock()

        # Mock photo object
        mock_photo = MagicMock()
        mock_photo.file_id = "fake_file_id"
        update.effective_message.photo = [mock_photo]  # List of sizes, last is largest

        context = MagicMock()
        mock_file = AsyncMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"\x89PNG fake"))
        context.bot = AsyncMock()
        context.bot.get_file = AsyncMock(return_value=mock_file)

        await bot._handle_photo(update, context)

        update.effective_message.reply_text.assert_called_once()
        msg = update.effective_message.reply_text.call_args[0][0]
        assert "Photo avatar set" in msg
        assert store.get_avatar_path(child["id"]) is not None

    @pytest.mark.asyncio
    async def test_photo_no_caption_ignored(self, bot, store):
        """Photo without 'avatar' caption is silently ignored."""
        store.add_child("Alex")

        update = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user.id = 12345
        update.effective_message = MagicMock()
        update.effective_message.caption = "Just a random photo"
        update.effective_message.reply_text = AsyncMock()
        update.effective_message.photo = [MagicMock()]

        context = MagicMock()

        await bot._handle_photo(update, context)
        update.effective_message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_photo_child_not_found(self, bot, store):
        update = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user.id = 12345
        update.effective_message = MagicMock()
        update.effective_message.caption = "avatar Ghost"
        update.effective_message.reply_text = AsyncMock()
        update.effective_message.photo = [MagicMock()]

        context = MagicMock()

        await bot._handle_photo(update, context)
        msg = update.effective_message.reply_text.call_args[0][0]
        assert "not found" in msg

    @pytest.mark.asyncio
    async def test_photo_non_admin_ignored(self, bot, store):
        store.add_child("Alex")
        update = MagicMock()
        update.effective_chat.id = 99999
        update.effective_user.id = 99999
        update.effective_message = MagicMock()
        update.effective_message.caption = "avatar Alex"
        update.effective_message.reply_text = AsyncMock()
        update.effective_message.photo = [MagicMock()]

        context = MagicMock()
        await bot._handle_photo(update, context)
        update.effective_message.reply_text.assert_not_called()


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
    async def test_channel_list_empty(self, bot, admin_update, context, store):
        store.add_child("Alex")  # single child — name can be omitted
        context.args = []
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "No channels" in msg

    @pytest.mark.asyncio
    async def test_channel_allow(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        context.args = ["allow", "GoodChannel", "edu"]
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "allowed" in msg
        assert store.is_channel_allowed(child["id"], "GoodChannel")

    @pytest.mark.asyncio
    async def test_channel_block(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        context.args = ["block", "BadChannel"]
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "blocked" in msg
        assert store.is_channel_blocked(child["id"], "BadChannel")

    @pytest.mark.asyncio
    async def test_channel_unallow(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "TestCh", "allowed")
        context.args = ["unallow", "TestCh"]
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Removed" in msg
        assert not store.is_channel_allowed(child["id"], "TestCh")

    @pytest.mark.asyncio
    async def test_channel_unblock(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "BadCh", "blocked")
        context.args = ["unblock", "BadCh"]
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Removed" in msg

    @pytest.mark.asyncio
    async def test_channel_list_with_channels(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Allowed1", "allowed")
        store.add_channel(child["id"], "Blocked1", "blocked")
        context.args = []
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Allowed Channels" in msg
        assert "Blocked Channels" in msg

    @pytest.mark.asyncio
    async def test_channel_invalid_subcmd(self, bot, admin_update, context, store):
        store.add_child("Alex")
        context.args = ["invalid"]
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Usage:" in msg

    @pytest.mark.asyncio
    async def test_channel_unallow_includes_video_count(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "TestCh", "allowed")
        store.add_video("vid_a_12345", "Video A", "TestCh")
        store.add_video("vid_b_12345", "Video B", "TestCh")
        store.request_video(cid, "vid_a_12345")
        store.request_video(cid, "vid_b_12345")
        context.args = ["unallow", "TestCh"]
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "2 associated video(s)" in msg

    @pytest.mark.asyncio
    async def test_channel_unallow_zero_videos(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "EmptyCh", "allowed")
        context.args = ["unallow", "EmptyCh"]
        await bot._cmd_channel(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "no associated videos" in msg

    @pytest.mark.asyncio
    async def test_channel_list_renders_delete_buttons(self, bot, admin_update, context, store):
        child = store.add_child("Alex")
        store.add_channel(child["id"], "Allowed1", "allowed")
        store.add_channel(child["id"], "Blocked1", "blocked")
        context.args = []
        await bot._cmd_channel(admin_update, context)
        # Check that reply_markup has delete buttons
        call_kwargs = admin_update.effective_message.reply_text.call_args[1]
        keyboard = call_kwargs["reply_markup"]
        # Flatten all button callback_data values
        all_data = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
        assert any("chan_del:" in d for d in all_data)
        # Each channel should have a delete button
        assert any("Allowed1" in d for d in all_data)
        assert any("Blocked1" in d for d in all_data)


# ── Channel Delete Callback ──────────────────────────────────────

class TestChannelDeleteCallback:
    def _make_callback_update(self, data: str):
        update = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user.id = 12345
        update.callback_query = AsyncMock()
        update.callback_query.data = data
        update.callback_query.answer = AsyncMock()
        update.callback_query.message = AsyncMock()
        return update

    @pytest.mark.asyncio
    async def test_chan_del_shows_confirmation(self, bot, store, context):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "TestCh", "allowed")
        store.add_video("vid_a_12345", "Video A", "TestCh")
        store.request_video(cid, "vid_a_12345")

        update = self._make_callback_update(f"chan_del:{cid}:0:TestCh")
        await bot._handle_callback(update, context)

        # Should show confirmation with video count
        msg = update.callback_query.message.edit_text.call_args
        text = msg[0][0]
        assert "Remove" in text
        assert "TestCh" in text
        assert "1" in text  # 1 associated video
        # Should have Yes/Cancel buttons
        keyboard = msg[1]["reply_markup"]
        all_data = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
        assert any("chan_del_yes:" in d for d in all_data)
        assert any("chan_del_no:" in d for d in all_data)

    @pytest.mark.asyncio
    async def test_chan_del_yes_removes_and_refreshes(self, bot, store, context):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "TestCh", "allowed")
        store.add_video("vid_a_12345", "Video A", "TestCh")
        store.request_video(cid, "vid_a_12345")

        update = self._make_callback_update(f"chan_del_yes:{cid}:0:TestCh")
        await bot._handle_callback(update, context)

        # Channel should be removed
        assert not store.is_channel_allowed(cid, "TestCh")
        # Should have answered with removal info
        update.callback_query.answer.assert_called()

    @pytest.mark.asyncio
    async def test_chan_del_no_returns_to_list(self, bot, store, context):
        child = store.add_child("Alex")
        cid = child["id"]
        store.add_channel(cid, "TestCh", "allowed")

        update = self._make_callback_update(f"chan_del_no:{cid}:0")
        await bot._handle_callback(update, context)

        # Channel should still exist
        assert store.is_channel_allowed(cid, "TestCh")
        # Should have refreshed the channel list view
        msg_text = update.callback_query.message.edit_text.call_args[0][0]
        assert "Allowed Channels" in msg_text


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

        assert store.is_channel_allowed(child["id"], "GoodChannel")
        assert store.get_video_status(child["id"], "vid12345678") == "approved"

    @pytest.mark.asyncio
    async def test_blockchan(self, bot, store, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "BadChannel")
        store.request_video(child["id"], "vid12345678")

        update = self._make_callback_update(f"blockchan:{child['id']}:vid12345678")
        await bot._handle_callback(update, context)

        assert store.is_channel_blocked(child["id"], "BadChannel")
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


# ── Channel Video Import ──────────────────────────────────────────

class TestChannelVideoImport:
    """Tests for bulk channel video import when a channel is allowed."""

    def _make_callback_update(self, data: str):
        update = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user.id = 12345
        update.callback_query = AsyncMock()
        update.callback_query.data = data
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_caption = AsyncMock()
        update.callback_query.message = AsyncMock()
        return update

    @pytest.mark.asyncio
    async def test_allowchan_imports_channel_videos(self, store, cfg, context):
        """Allowing a channel should import videos for the requesting child only."""
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.add_video("vid12345678", "Trigger Video", "GoodChannel", channel_id="UC123")
        store.request_video(alex["id"], "vid12345678")

        mock_inv = AsyncMock()
        mock_inv.get_channel_videos = AsyncMock(return_value=[
            {"video_id": "ch_vid1", "title": "Ch Video 1", "channel_name": "GoodChannel", "channel_id": "UC123", "duration": 120},
            {"video_id": "ch_vid2", "title": "Ch Video 2", "channel_name": "GoodChannel", "channel_id": "UC123", "duration": 240},
        ])
        bot = TelegramBot("fake-token", "12345", store, cfg, inv_client=mock_inv)

        update = self._make_callback_update(f"allowchan_edu:{alex['id']}:vid12345678")
        await bot._handle_callback(update, context)

        assert store.is_channel_allowed(alex["id"], "GoodChannel")
        assert store.get_video_status(alex["id"], "vid12345678") == "approved"
        # Imported videos should exist and be approved for requesting child only
        assert store.get_video("ch_vid1") is not None
        assert store.get_video("ch_vid2") is not None
        assert store.get_video_status(alex["id"], "ch_vid1") == "approved"
        assert store.get_video_status(alex["id"], "ch_vid2") == "approved"
        # Sam should NOT have access (channel is per-child)
        assert store.get_video_status(sam["id"], "ch_vid1") is None
        assert store.get_video_status(sam["id"], "ch_vid2") is None
        # Confirmation should mention import count
        caption = update.callback_query.edit_message_caption.call_args[1]["caption"]
        assert "2 channel videos imported" in caption

    @pytest.mark.asyncio
    async def test_allowchan_import_failure_still_allows_channel(self, store, cfg, context):
        """If Invidious fails, the channel should still be allowed."""
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Trigger Video", "FailChannel", channel_id="UC_FAIL")
        store.request_video(child["id"], "vid12345678")

        mock_inv = AsyncMock()
        mock_inv.get_channel_videos = AsyncMock(side_effect=Exception("Invidious down"))
        bot = TelegramBot("fake-token", "12345", store, cfg, inv_client=mock_inv)

        update = self._make_callback_update(f"allowchan_edu:{child['id']}:vid12345678")
        await bot._handle_callback(update, context)

        assert store.is_channel_allowed(child["id"], "FailChannel")
        assert store.get_video_status(child["id"], "vid12345678") == "approved"

    @pytest.mark.asyncio
    async def test_allowchan_no_inv_client(self, bot, store, context):
        """Bot without inv_client should still allow channel (no import)."""
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Video", "Channel", channel_id="UC1")
        store.request_video(child["id"], "vid12345678")

        assert bot.inv_client is None
        update = self._make_callback_update(f"allowchan_edu:{child['id']}:vid12345678")
        await bot._handle_callback(update, context)

        assert store.is_channel_allowed(child["id"], "Channel")
        assert store.get_video_status(child["id"], "vid12345678") == "approved"

    @pytest.mark.asyncio
    async def test_allowchan_no_channel_id_skips_import(self, store, cfg, context):
        """If video has no channel_id, import is skipped but channel is still allowed."""
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Video", "Channel")  # No channel_id
        store.request_video(child["id"], "vid12345678")

        mock_inv = AsyncMock()
        bot = TelegramBot("fake-token", "12345", store, cfg, inv_client=mock_inv)

        update = self._make_callback_update(f"allowchan_fun:{child['id']}:vid12345678")
        await bot._handle_callback(update, context)

        assert store.is_channel_allowed(child["id"], "Channel")
        assert store.get_video_status(child["id"], "vid12345678") == "approved"
        mock_inv.get_channel_videos.assert_not_called()


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

        assert store.is_channel_allowed(alex["id"], "NewChannel")
        assert not store.is_channel_allowed(sam["id"], "NewChannel")
        assert store.get_video_status(alex["id"], "vid12345678") == "approved"
        # Sam's request remains pending (channel is allowed for Alex only)
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


class TestChildCommand:
    """Tests for the /child combined management command (#15)."""

    @pytest.mark.asyncio
    async def test_child_no_args_lists_kids(self, bot, store, admin_update, context):
        store.add_child("Alex")
        store.add_child("Sam")
        context.args = []
        await bot._cmd_child(admin_update, context)
        admin_update.effective_message.reply_text.assert_called_once()
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Alex" in text
        assert "Sam" in text

    @pytest.mark.asyncio
    async def test_child_add(self, bot, store, admin_update, context):
        context.args = ["add", "Alex"]
        await bot._cmd_child(admin_update, context)
        assert store.get_child_by_name("Alex") is not None
        text = admin_update.effective_message.reply_text.call_args_list[0][0][0]
        assert "Alex" in text
        assert "created" in text

    @pytest.mark.asyncio
    async def test_child_add_with_avatar(self, bot, store, admin_update, context):
        context.args = ["add", "Sam", "\U0001f467"]
        await bot._cmd_child(admin_update, context)
        child = store.get_child_by_name("Sam")
        assert child is not None
        assert child["avatar"] == "\U0001f467"

    @pytest.mark.asyncio
    async def test_child_remove(self, bot, store, admin_update, context):
        store.add_child("Alex")
        context.args = ["remove", "Alex"]
        await bot._cmd_child(admin_update, context)
        assert store.get_child_by_name("Alex") is None
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "removed" in text

    @pytest.mark.asyncio
    async def test_child_rename(self, bot, store, admin_update, context):
        store.add_child("Alex")
        context.args = ["rename", "Alex", "Alexander"]
        await bot._cmd_child(admin_update, context)
        assert store.get_child_by_name("Alex") is None
        assert store.get_child_by_name("Alexander") is not None

    @pytest.mark.asyncio
    async def test_child_show_profile(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")
        store.add_video("vid1", "V1", "Ch")
        store.request_video(child["id"], "vid1")
        store.update_video_status(child["id"], "vid1", "approved")
        context.args = ["Alex"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Alex" in text
        assert "1 approved" in text

    @pytest.mark.asyncio
    async def test_child_not_found(self, bot, store, admin_update, context):
        context.args = ["NonExistent"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "not found" in text

    @pytest.mark.asyncio
    async def test_child_language_set(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        context.args = ["language", "Alex", "es"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "es" in text
        assert store.get_child_setting(child["id"], "preferred_language") == "es"

    @pytest.mark.asyncio
    async def test_child_language_clear_off(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "preferred_language", "es")
        context.args = ["language", "Alex", "off"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "cleared" in text
        assert store.get_child_setting(child["id"], "preferred_language") == ""

    @pytest.mark.asyncio
    async def test_child_language_clear_default(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "preferred_language", "fr")
        context.args = ["language", "Alex", "default"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "cleared" in text
        assert store.get_child_setting(child["id"], "preferred_language") == ""

    @pytest.mark.asyncio
    async def test_child_language_not_found(self, bot, store, admin_update, context):
        context.args = ["language", "Ghost", "en"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "not found" in text

    @pytest.mark.asyncio
    async def test_child_language_no_args(self, bot, store, admin_update, context):
        context.args = ["language"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Usage:" in text

    @pytest.mark.asyncio
    async def test_child_profile_shows_language(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")
        store.set_child_setting(child["id"], "preferred_language", "es")
        context.args = ["Alex"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Language:" in text
        assert "es" in text

    @pytest.mark.asyncio
    async def test_child_profile_shows_global_default_language(self, bot, store, admin_update, context, cfg):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")
        cfg.preferred_audio_lang = "en"
        context.args = ["Alex"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Language:" in text
        assert "en (global default)" in text
        cfg.preferred_audio_lang = ""  # reset

    @pytest.mark.asyncio
    async def test_child_profile_shows_not_set_language(self, bot, store, admin_update, context, cfg):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")
        cfg.preferred_audio_lang = ""
        context.args = ["Alex"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Language:" in text
        assert "not set" in text


class TestCombinedStats:
    """Tests for combined /stats view with multiple children (#15)."""

    @pytest.mark.asyncio
    async def test_stats_combined_multi_child(self, bot, store, admin_update, context):
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.set_child_setting(alex["id"], "daily_limit_minutes", "60")
        store.set_child_setting(sam["id"], "daily_limit_minutes", "90")
        store.add_video("v1", "V1", "Ch")
        store.add_video("v2", "V2", "Ch")
        store.request_video(alex["id"], "v1")
        store.request_video(sam["id"], "v2")

        context.args = []
        await bot._cmd_stats(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "All Children" in text
        assert "Alex" in text
        assert "Sam" in text

    @pytest.mark.asyncio
    async def test_stats_single_child_no_args(self, bot, store, admin_update, context):
        store.add_child("Alex")
        context.args = []
        await bot._cmd_stats(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Overall Stats" in text


class TestCombinedWatch:
    """Tests for combined /watch view with multiple children (#15)."""

    @pytest.mark.asyncio
    async def test_watch_combined_multi_child(self, bot, store, admin_update, context):
        alex = store.add_child("Alex")
        sam = store.add_child("Sam")
        store.add_video("v1", "Video One", "Ch")
        store.record_watch_seconds("v1", alex["id"], 120)
        store.record_watch_seconds("v1", sam["id"], 60)

        context.args = []
        await bot._cmd_watch(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "All Children" in text
        assert "Alex" in text
        assert "Sam" in text

    @pytest.mark.asyncio
    async def test_watch_combined_no_activity(self, bot, store, admin_update, context):
        store.add_child("Alex")
        store.add_child("Sam")
        context.args = []
        await bot._cmd_watch(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "No watch activity" in text


class TestStarterChannelsBot:
    """Tests for starter channels in the Telegram bot (#13)."""

    def test_load_starter_channels(self, bot):
        data = bot._load_starter_channels()
        assert "educational" in data
        assert "fun" in data
        assert len(data["educational"]) > 0

    @pytest.mark.asyncio
    async def test_channel_starter_subcommand(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        context.args = ["starter"]
        # Need to set up _resolve_child properly
        context.args = ["Alex", "starter"]
        await bot._cmd_channel(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Starter Channels" in text


# ── Starter Channel Auto-Prompt (#40) ─────────────────────────────

class TestStarterAutoPrompt:
    """Tests for auto-prompting starter channels after child creation (#40)."""

    @pytest.mark.asyncio
    async def test_addkid_zero_channels_triggers_starter_prompt(self, bot, admin_update, context, store):
        """Creating a child with zero channels triggers the starter prompt."""
        context.args = ["Alex"]
        await bot._cmd_addkid(admin_update, context)
        # Should have two reply_text calls: profile created + starter prompt
        calls = admin_update.effective_message.reply_text.call_args_list
        assert len(calls) == 2
        prompt_text = calls[1][0][0]
        assert "kid-friendly channels" in prompt_text
        assert "Alex" in prompt_text
        # Check inline button present
        prompt_kwargs = calls[1][1]
        keyboard = prompt_kwargs["reply_markup"]
        assert "starter_page" in keyboard.inline_keyboard[0][0].callback_data

    @pytest.mark.asyncio
    async def test_addkid_existing_channels_skips_prompt(self, bot, admin_update, context, store):
        """Creating a child when channels already exist does not trigger prompt."""
        child = store.add_child("Alex")
        store.add_channel(child["id"], "SomeChannel", "allowed", handle="@somechannel")
        store.remove_child(child["id"])
        # Now create via /addkid — we need to pre-add channels after creation
        # Instead, test via _maybe_prompt_starter_channels directly
        child2 = store.add_child("Alex")
        store.add_channel(child2["id"], "SomeChannel", "allowed", handle="@somechannel")
        msg = AsyncMock()
        msg.reply_text = AsyncMock()
        await bot._maybe_prompt_starter_channels(msg, child2["id"], "Alex")
        msg.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_starter_prompt_not_repeated(self, bot, admin_update, context, store):
        """Prompt is not repeated on subsequent interactions."""
        context.args = ["Alex"]
        await bot._cmd_addkid(admin_update, context)
        child = store.get_child_by_name("Alex")
        # Prompt was sent — flag should be set
        assert store.get_child_setting(child["id"], "starter_prompted") == "1"
        # Call again directly — should not send
        msg = AsyncMock()
        msg.reply_text = AsyncMock()
        await bot._maybe_prompt_starter_channels(msg, child["id"], "Alex")
        msg.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_child_add_subcommand_triggers_starter_prompt(self, bot, admin_update, context, store):
        """Creating a child via /child add also triggers the starter prompt."""
        context.args = ["add", "Sam"]
        await bot._cmd_child(admin_update, context)
        calls = admin_update.effective_message.reply_text.call_args_list
        assert len(calls) == 2
        prompt_text = calls[1][0][0]
        assert "kid-friendly channels" in prompt_text
        assert "Sam" in prompt_text

    @pytest.mark.asyncio
    async def test_start_no_children_suggests_addkid(self, bot, admin_update, context):
        """On first interaction with no children, /start suggests /addkid."""
        context.args = []
        await bot._cmd_help(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "/addkid" in msg
        assert "don't have any child profiles" in msg

    @pytest.mark.asyncio
    async def test_start_with_children_shows_help(self, bot, admin_update, context, store):
        """/start with existing children shows normal help text."""
        store.add_child("Alex")
        context.args = []
        await bot._cmd_help(admin_update, context)
        msg = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Bot Commands" in msg
        assert "/addkid" not in msg or "/child add" in msg


# ── Pending List Actions (#29) ────────────────────────────────────

class TestPendingActions:
    """Tests for inline approve/deny buttons on the /pending list (#29)."""

    def _make_callback_update(self, data: str):
        update = MagicMock()
        update.effective_chat.id = 12345
        update.effective_user.id = 12345
        update.callback_query = AsyncMock()
        update.callback_query.data = data
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_caption = AsyncMock()
        update.callback_query.message = AsyncMock()
        return update

    @pytest.mark.asyncio
    async def test_pending_list_shows_action_buttons(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "Channel", duration=120)
        store.request_video(child["id"], "vid12345678")

        context.args = []
        await bot._cmd_pending(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Pending Requests" in text
        assert "Test Video" in text

    @pytest.mark.asyncio
    async def test_pnd_edu_approves_from_pending_list(self, bot, store, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "Channel")
        store.request_video(child["id"], "vid12345678")

        update = self._make_callback_update(f"pnd_edu:{child['id']}:0:vid12345678")
        await bot._handle_callback(update, context)

        assert store.get_video_status(child["id"], "vid12345678") == "approved"
        video = store.get_video("vid12345678")
        assert video["category"] == "edu"

    @pytest.mark.asyncio
    async def test_pnd_fun_approves_from_pending_list(self, bot, store, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "Channel")
        store.request_video(child["id"], "vid12345678")

        update = self._make_callback_update(f"pnd_fun:{child['id']}:0:vid12345678")
        await bot._handle_callback(update, context)

        assert store.get_video_status(child["id"], "vid12345678") == "approved"
        video = store.get_video("vid12345678")
        assert video["category"] == "fun"

    @pytest.mark.asyncio
    async def test_pnd_deny_from_pending_list(self, bot, store, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "Channel")
        store.request_video(child["id"], "vid12345678")

        update = self._make_callback_update(f"pnd_deny:{child['id']}:0:vid12345678")
        await bot._handle_callback(update, context)

        assert store.get_video_status(child["id"], "vid12345678") == "denied"

    @pytest.mark.asyncio
    async def test_pending_list_shows_resend_button(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "Channel", duration=120)
        store.request_video(child["id"], "vid12345678")

        context.args = []
        await bot._cmd_pending(admin_update, context)
        keyboard = admin_update.effective_message.reply_text.call_args[1]["reply_markup"]
        # First row of buttons is for the first pending item
        button_data = [btn.callback_data for btn in keyboard.inline_keyboard[0]]
        assert any("pnd_resend" in d for d in button_data)

    @pytest.mark.asyncio
    async def test_pnd_resend_triggers_notify(self, bot, store, context):
        child = store.add_child("Alex")
        store.add_video("vid12345678", "Test Video", "Channel")
        store.request_video(child["id"], "vid12345678")

        update = self._make_callback_update(f"pnd_resend:{child['id']}:0:vid12345678")
        bot.notify_new_request = AsyncMock()
        await bot._handle_callback(update, context)

        bot.notify_new_request.assert_called_once()
        call_args = bot.notify_new_request.call_args[0]
        assert call_args[0]["id"] == child["id"]
        assert call_args[1]["video_id"] == "vid12345678"
        # Video should still be pending (resend doesn't change status)
        assert store.get_video_status(child["id"], "vid12345678") == "pending"


# ── Free Day Pass (#32) ──────────────────────────────────────────

class TestFreeDayCommand:
    """Tests for /freeday command (#32)."""

    @pytest.mark.asyncio
    async def test_freeday_grants_pass(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        context.args = ["Alex"]
        await bot._cmd_freeday(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "granted" in text

        free_day = store.get_child_setting(child["id"], "free_day_date", "")
        assert free_day != ""  # Should be today's date

    @pytest.mark.asyncio
    async def test_freeday_toggle_revokes(self, bot, store, admin_update, context):
        from utils import get_today_str
        child = store.add_child("Alex")
        tz = bot.config.watch_limits.timezone
        today = get_today_str(tz)
        store.set_child_setting(child["id"], "free_day_date", today)

        context.args = ["Alex"]
        await bot._cmd_freeday(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "revoked" in text
        assert store.get_child_setting(child["id"], "free_day_date", "") == ""

    @pytest.mark.asyncio
    async def test_freeday_off(self, bot, store, admin_update, context):
        from utils import get_today_str
        child = store.add_child("Alex")
        tz = bot.config.watch_limits.timezone
        today = get_today_str(tz)
        store.set_child_setting(child["id"], "free_day_date", today)

        context.args = ["Alex", "off"]
        await bot._cmd_freeday(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "revoked" in text

    @pytest.mark.asyncio
    async def test_freeday_single_child_default(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        context.args = []
        await bot._cmd_freeday(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "granted" in text

    @pytest.mark.asyncio
    async def test_freeday_multi_child_requires_name(self, bot, store, admin_update, context):
        store.add_child("Alex")
        store.add_child("Sam")
        context.args = []
        await bot._cmd_freeday(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Specify a child" in text

    @pytest.mark.asyncio
    async def test_time_status_shows_free_day(self, bot, store, admin_update, context):
        from utils import get_today_str
        child = store.add_child("Alex")
        tz = bot.config.watch_limits.timezone
        today = get_today_str(tz)
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")
        store.set_child_setting(child["id"], "free_day_date", today)

        await bot._show_time_status(admin_update.effective_message, child)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "unlimited" in text
        assert "ACTIVE" in text


class TestFamilySafeFilter:
    """Tests for /child familysafe command and notification warning (#34)."""

    @pytest.mark.asyncio
    async def test_familysafe_on(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        context.args = ["familysafe", "Alex", "on"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "enabled" in text
        assert store.get_child_setting(child["id"], "family_safe_filter") == "on"

    @pytest.mark.asyncio
    async def test_familysafe_off(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        context.args = ["familysafe", "Alex", "off"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "disabled" in text
        assert store.get_child_setting(child["id"], "family_safe_filter") == "off"

    @pytest.mark.asyncio
    async def test_familysafe_invalid_value(self, bot, store, admin_update, context):
        store.add_child("Alex")
        context.args = ["familysafe", "Alex", "maybe"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "on" in text and "off" in text

    @pytest.mark.asyncio
    async def test_familysafe_missing_args(self, bot, store, admin_update, context):
        store.add_child("Alex")
        context.args = ["familysafe"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Usage" in text

    @pytest.mark.asyncio
    async def test_familysafe_child_not_found(self, bot, store, admin_update, context):
        context.args = ["familysafe", "Ghost", "on"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "not found" in text

    @pytest.mark.asyncio
    async def test_child_summary_shows_filter_state(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")
        context.args = ["Alex"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Family Safe Filter" in text
        assert "on" in text

    @pytest.mark.asyncio
    async def test_child_summary_shows_filter_off(self, bot, store, admin_update, context):
        child = store.add_child("Alex")
        store.set_child_setting(child["id"], "daily_limit_minutes", "60")
        store.set_child_setting(child["id"], "family_safe_filter", "off")
        context.args = ["Alex"]
        await bot._cmd_child(admin_update, context)
        text = admin_update.effective_message.reply_text.call_args[0][0]
        assert "Family Safe Filter" in text
        assert "off" in text

    @pytest.mark.asyncio
    async def test_notify_warns_non_family_friendly(self, bot, store):
        """Notification includes warning for non-family-friendly videos."""
        child = store.add_child("Alex")
        video = {
            "video_id": "abc12345678",
            "title": "Test Video",
            "channel_name": "Test Channel",
            "duration": 300,
            "thumbnail_url": "",
        }

        bot._app = MagicMock()
        bot._app.bot = AsyncMock()
        bot._app.bot.send_message = AsyncMock()

        mock_inv_client = AsyncMock()
        mock_inv_client.get_video = AsyncMock(return_value={
            "video_id": "abc12345678",
            "is_family_friendly": False,
        })
        bot.inv_client = mock_inv_client

        await bot.notify_new_request(child, video)
        bot._app.bot.send_message.assert_called_once()
        call_kwargs = bot._app.bot.send_message.call_args[1]
        assert "Not marked as family-friendly" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_notify_no_warning_for_family_friendly(self, bot, store):
        """No warning when video is family-friendly."""
        child = store.add_child("Alex")
        video = {
            "video_id": "abc12345678",
            "title": "Test Video",
            "channel_name": "Test Channel",
            "duration": 300,
            "thumbnail_url": "",
        }

        bot._app = MagicMock()
        bot._app.bot = AsyncMock()
        bot._app.bot.send_message = AsyncMock()

        mock_inv_client = AsyncMock()
        mock_inv_client.get_video = AsyncMock(return_value={
            "video_id": "abc12345678",
            "is_family_friendly": True,
        })
        bot.inv_client = mock_inv_client

        await bot.notify_new_request(child, video)
        bot._app.bot.send_message.assert_called_once()
        call_kwargs = bot._app.bot.send_message.call_args[1]
        assert "Not marked as family-friendly" not in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_notify_warning_without_inv_client(self, bot, store):
        """No crash when inv_client is None."""
        child = store.add_child("Alex")
        video = {
            "video_id": "abc12345678",
            "title": "Test Video",
            "channel_name": "Test Channel",
            "thumbnail_url": "",
        }

        bot._app = MagicMock()
        bot._app.bot = AsyncMock()
        bot._app.bot.send_message = AsyncMock()
        bot.inv_client = None

        await bot.notify_new_request(child, video)
        bot._app.bot.send_message.assert_called_once()
