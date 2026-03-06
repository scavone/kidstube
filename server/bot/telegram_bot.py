"""Telegram bot for parental controls — multi-child support.

Adapted from BrainRotGuard's single-child bot to support multiple children.
Callback data pattern: action:childId:videoId (child context embedded).
Commands accept optional child name; default to only child if single.
"""

import asyncio
import logging
from io import BytesIO
from pathlib import Path
from typing import Optional, Callable, Awaitable

import httpx
import yaml
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

from data.video_store import VideoStore
from utils import (
    get_today_str,
    get_day_utc_bounds,
    parse_time_input,
    format_time_12h,
    is_within_schedule,
    format_duration,
)

logger = logging.getLogger(__name__)

# Pagination sizes
_PENDING_PAGE_SIZE = 5
_APPROVED_PAGE_SIZE = 10
_CHANNEL_PAGE_SIZE = 10
_STARTER_PAGE_SIZE = 10

# Thumbnail domain whitelist
_THUMB_HOSTS = {"i.ytimg.com", "i9.ytimg.com", "img.youtube.com"}


def _esc(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _progress_bar(fraction: float, width: int = 10) -> str:
    """Render a text progress bar."""
    filled = int(round(fraction * width))
    filled = max(0, min(filled, width))
    empty = width - filled
    return "[" + "=" * filled + "-" * empty + "]"


class TelegramBot:
    """Parent-facing Telegram bot with multi-child profile support."""

    def __init__(
        self,
        bot_token: str,
        admin_chat_id: str,
        video_store: VideoStore,
        config,
        inv_client=None,
    ):
        self.bot_token = bot_token
        self.admin_chat_id = int(admin_chat_id) if admin_chat_id else 0
        self.video_store = video_store
        self.config = config
        self.inv_client = inv_client
        self._app = None

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self):
        """Build the telegram application and start polling."""
        if not self.bot_token:
            logger.warning("No Telegram bot token configured — bot disabled")
            return

        builder = ApplicationBuilder().token(self.bot_token)
        self._app = builder.build()

        # Register handlers
        handlers = [
            CommandHandler(["start", "help"], self._cmd_help),
            CommandHandler("kids", self._cmd_kids),
            CommandHandler("child", self._cmd_child),
            CommandHandler("addkid", self._cmd_addkid),
            CommandHandler("editkid", self._cmd_editkid),
            CommandHandler("removekid", self._cmd_removekid),
            CommandHandler("pending", self._cmd_pending),
            CommandHandler("approved", self._cmd_approved),
            CommandHandler("stats", self._cmd_stats),
            CommandHandler("channel", self._cmd_channel),
            CommandHandler("time", self._cmd_time),
            CommandHandler("watch", self._cmd_watch),
            CommandHandler("search", self._cmd_search),
            CommandHandler("freeday", self._cmd_freeday),
            MessageHandler(filters.PHOTO & ~filters.COMMAND, self._handle_photo),
            CallbackQueryHandler(self._handle_callback),
        ]
        for h in handlers:
            self._app.add_handler(h)

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started")

    async def stop(self):
        """Gracefully shut down the bot."""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot stopped")

    # ── Auth ───────────────────────────────────────────────────────

    def _is_admin(self, update: Update) -> bool:
        """Check if the message sender is the configured admin."""
        if not self.admin_chat_id:
            return False
        chat_id = update.effective_chat.id if update.effective_chat else 0
        user_id = update.effective_user.id if update.effective_user else 0
        return chat_id == self.admin_chat_id or user_id == self.admin_chat_id

    async def _check_admin(self, update: Update) -> bool:
        """Verify admin and send rejection if not authorized."""
        if self._is_admin(update):
            return True
        await update.effective_message.reply_text("Unauthorized.")
        return False

    # ── Child Resolution ───────────────────────────────────────────

    def _resolve_child(self, name: Optional[str] = None) -> Optional[dict]:
        """Resolve a child by name. If name is None and only one child exists, return that."""
        if name:
            return self.video_store.get_child_by_name(name)
        children = self.video_store.get_children()
        if len(children) == 1:
            return children[0]
        return None

    def _all_children(self) -> list[dict]:
        return self.video_store.get_children()

    # ── Notification (called from API routes) ──────────────────────

    async def notify_new_request(self, child: dict, video: dict):
        """Send a new video request notification to the admin.

        This is the callback invoked from api/routes.py when a child
        requests a video that requires approval.
        """
        if not self._app or not self.admin_chat_id:
            return

        child_id = child["id"]
        child_name = child.get("name", "Unknown")
        video_id = video.get("video_id", "")
        title = video.get("title", "Unknown")
        channel = video.get("channel_name", "Unknown")
        duration = video.get("duration")

        dur_str = format_duration(duration) if duration else ""
        caption = (
            f"<b>[{_esc(child_name)}] New Video Request</b>\n\n"
            f"<b>{_esc(title)}</b>\n"
            f"{_esc(channel)}"
        )
        if dur_str:
            caption += f" • {dur_str}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "Watch on YouTube",
                url=f"https://www.youtube.com/watch?v={video_id}",
            )],
            [
                InlineKeyboardButton("Approve (Edu)", callback_data=f"approve_edu:{child_id}:{video_id}"),
                InlineKeyboardButton("Approve (Fun)", callback_data=f"approve_fun:{child_id}:{video_id}"),
            ],
            [InlineKeyboardButton("Deny", callback_data=f"deny:{child_id}:{video_id}")],
            [
                InlineKeyboardButton("Allow Ch (Edu)", callback_data=f"allowchan_edu:{child_id}:{video_id}"),
                InlineKeyboardButton("Allow Ch (Fun)", callback_data=f"allowchan_fun:{child_id}:{video_id}"),
            ],
            [InlineKeyboardButton("Block Channel", callback_data=f"blockchan:{child_id}:{video_id}")],
        ])

        # Try to send with thumbnail
        thumb_url = video.get("thumbnail_url", "")
        sent = False
        if thumb_url:
            try:
                async with httpx.AsyncClient(timeout=5.0) as http:
                    resp = await http.get(thumb_url)
                    if resp.status_code == 200:
                        await self._app.bot.send_photo(
                            chat_id=self.admin_chat_id,
                            photo=BytesIO(resp.content),
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=keyboard,
                        )
                        sent = True
            except Exception:
                logger.debug("Thumbnail fetch failed for %s, falling back to text", video_id)

        if not sent:
            await self._app.bot.send_message(
                chat_id=self.admin_chat_id,
                text=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )

    # ── Callback Handler ───────────────────────────────────────────

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Route inline button callbacks."""
        query = update.callback_query
        if not query or not query.data:
            return
        if not self._is_admin(update):
            await query.answer("Unauthorized")
            return

        await query.answer()
        data = query.data
        parts = data.split(":")

        action = parts[0]

        # Pagination callbacks (no child/video context)
        if action == "pending_page" and len(parts) >= 2:
            page = int(parts[1])
            await self._show_pending_page(query.message, page)
            return
        if action == "approved_page" and len(parts) >= 3:
            child_id = int(parts[1])
            page = int(parts[2])
            await self._show_approved_page(query.message, child_id, page)
            return
        if action == "chan_page" and len(parts) >= 3:
            child_id = int(parts[1])
            page = int(parts[2])
            await self._show_channel_page(query.message, child_id, page)
            return
        # Starter channel pagination: starter_page:child_id:page
        if action == "starter_page" and len(parts) >= 3:
            child_id = int(parts[1])
            page = int(parts[2])
            await self._show_starter_page(query.message, child_id, page)
            return

        # Starter channel import: starter_import:child_id:handle
        if action == "starter_import" and len(parts) >= 3:
            child_id = int(parts[1])
            handle = ":".join(parts[2:])
            await self._import_starter_channel(query, child_id, handle)
            return

        # Pending list actions: pnd_edu/pnd_fun/pnd_deny:child_id:page:video_id
        if action in ("pnd_edu", "pnd_fun", "pnd_deny") and len(parts) >= 4:
            child_id = int(parts[1])
            page = int(parts[2])
            video_id = ":".join(parts[3:])
            if action == "pnd_deny":
                self.video_store.update_video_status(child_id, video_id, "denied")
            else:
                category = "edu" if action == "pnd_edu" else "fun"
                self.video_store.update_video_status(child_id, video_id, "approved")
                self._set_video_category(video_id, category)
            await self._show_pending_page(query.message, page)
            return

        # Revoke from approved list: rev:child_id:page:video_id
        if action == "rev" and len(parts) >= 4:
            child_id = int(parts[1])
            page = int(parts[2])
            video_id = ":".join(parts[3:])
            self.video_store.update_video_status(child_id, video_id, "denied")
            await self._show_approved_page(query.message, child_id, page)
            return

        # Approval/denial actions: action:child_id:video_id
        if len(parts) < 3:
            return
        child_id = int(parts[1])
        video_id = ":".join(parts[2:])  # video_id may contain colons (unlikely but safe)

        child = self.video_store.get_child(child_id)
        child_name = child["name"] if child else f"Child#{child_id}"
        video = self.video_store.get_video(video_id)
        video_title = video["title"] if video else video_id

        if action in ("approve_edu", "approve_fun"):
            category = "edu" if action == "approve_edu" else "fun"
            self.video_store.update_video_status(child_id, video_id, "approved")
            # Set video category
            if video:
                self._set_video_category(video_id, category)
            label = "Educational" if category == "edu" else "Entertainment"
            await query.edit_message_caption(
                caption=f"Approved ({label}) for {_esc(child_name)}: <b>{_esc(video_title)}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Revoke", callback_data=f"revoke:{child_id}:{video_id}"),
                ]]),
            )

        elif action == "deny":
            self.video_store.update_video_status(child_id, video_id, "denied")
            await query.edit_message_caption(
                caption=f"Denied for {_esc(child_name)}: <b>{_esc(video_title)}</b>",
                parse_mode=ParseMode.HTML,
            )

        elif action == "revoke":
            self.video_store.update_video_status(child_id, video_id, "denied")
            await query.edit_message_caption(
                caption=f"Revoked for {_esc(child_name)}: <b>{_esc(video_title)}</b>",
                parse_mode=ParseMode.HTML,
            )

        elif action == "allowchan_edu" or action == "allowchan_fun":
            category = "edu" if action == "allowchan_edu" else "fun"
            if video:
                ch_name = video["channel_name"]
                ch_id = video.get("channel_id")
                self.video_store.add_channel(child_id, ch_name, "allowed", channel_id=ch_id, category=category)
                # Auto-approve this video for the requesting child
                self.video_store.update_video_status(child_id, video_id, "approved")
                self._set_video_category(video_id, category)

                # Best-effort: import channel videos for this child
                import_count = 0
                if self.inv_client and ch_id:
                    try:
                        channel_videos = await self.inv_client.get_channel_videos(ch_id)
                        import_count = self.video_store.bulk_import_channel_videos(
                            channel_videos, category, [child_id]
                        )
                        logger.info(
                            "Imported %d videos from channel %s for child %d",
                            import_count, ch_name, child_id,
                        )
                    except Exception:
                        logger.warning(
                            "Failed to import channel videos for %s (best-effort)",
                            ch_name,
                            exc_info=True,
                        )

                label = "Educational" if category == "edu" else "Entertainment"
                import_note = f"\n{import_count} channel videos imported." if import_count > 0 else ""
                await query.edit_message_caption(
                    caption=(
                        f"Channel <b>{_esc(ch_name)}</b> allowed ({label}) for {_esc(child_name)}.\n"
                        f"Video approved.{import_note}"
                    ),
                    parse_mode=ParseMode.HTML,
                )

        elif action == "blockchan":
            if video:
                ch_name = video["channel_name"]
                ch_id = video.get("channel_id")
                self.video_store.add_channel(child_id, ch_name, "blocked", channel_id=ch_id)
                self.video_store.update_video_status(child_id, video_id, "denied")
                await query.edit_message_caption(
                    caption=(
                        f"Channel <b>{_esc(ch_name)}</b> blocked for {_esc(child_name)}.\n"
                        f"Video denied."
                    ),
                    parse_mode=ParseMode.HTML,
                )

        elif action == "resend":
            if video and child:
                await self.notify_new_request(child, video)

    def _set_video_category(self, video_id: str, category: str):
        """Update video category in the videos table."""
        with self.video_store._lock:
            self.video_store.conn.execute(
                "UPDATE videos SET category = ? WHERE video_id = ?",
                (category, video_id),
            )
            self.video_store.conn.commit()

    # ── Commands ───────────────────────────────────────────────────

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        app_name = self.config.app_name
        text = (
            f"<b>{_esc(app_name)} Bot Commands</b>\n\n"
            "<b>Children</b>\n"
            "/child — List all profiles with summary\n"
            "/child add Name [Avatar] — Add a child profile\n"
            "/child remove Name — Delete a profile\n"
            "/child rename Old New — Rename a profile\n"
            "/child Name — Show single profile details\n\n"
            "<b>Content</b>\n"
            "/pending — View pending video requests\n"
            "/approved [ChildName] — Approved videos\n"
            "/channel [ChildName] — Manage channel lists\n"
            "/channel [ChildName] starter — Browse starter channels\n"
            "/search — Manage word filters\n\n"
            "<b>Activity</b>\n"
            "/stats [ChildName] — Video statistics (combined if omitted)\n"
            "/watch [ChildName] — Watch activity (combined if omitted)\n"
            "/time [ChildName] — View/set time limits\n"
            "/freeday [ChildName] — Grant unlimited watch time today\n\n"
            "<i>Child name can be omitted if only one child exists.</i>\n"
            "<i>Send a photo with caption \"avatar ChildName\" to set a photo avatar.</i>"
        )
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

    async def _cmd_kids(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        children = self._all_children()
        if not children:
            await update.effective_message.reply_text(
                "No child profiles yet. Use /addkid Name to create one."
            )
            return

        tz = self.config.watch_limits.timezone
        today = get_today_str(tz)
        bounds = get_day_utc_bounds(today, tz)

        lines = [f"<b>Child Profiles ({len(children)})</b>\n"]
        for child in children:
            cid = child["id"]
            avatar = child.get("avatar", "")
            name = child["name"]

            # Time usage
            limit_str = self.video_store.get_child_setting(cid, "daily_limit_minutes", "")
            limit = int(limit_str) if limit_str else self.config.watch_limits.daily_limit_minutes
            used = self.video_store.get_daily_watch_minutes(cid, today, utc_bounds=bounds)

            # Pending count
            pending = self.video_store.get_pending_requests(child_id=cid)
            pending_count = len(pending)

            remaining = max(0, limit - used)
            bar = _progress_bar(used / limit if limit > 0 else 0)

            lines.append(
                f"{avatar} <b>{_esc(name)}</b>\n"
                f"  Time: {used:.0f}/{limit} min {bar}\n"
                f"  Remaining: {remaining:.0f} min"
                + (f" | Pending: {pending_count}" if pending_count > 0 else "")
            )

        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.HTML
        )

    async def _cmd_child(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Combined child management command.

        /child — list all profiles with summary
        /child add <name> [pin] — create profile
        /child remove <name> — delete profile
        /child rename <old> <new> — rename profile
        /child <name> — show single child profile summary
        """
        if not await self._check_admin(update):
            return

        args = context.args or []

        # /child (no args) — same as /kids
        if not args:
            await self._cmd_kids(update, context)
            return

        subcmd = args[0].lower()

        # /child add <name> [avatar]
        if subcmd == "add":
            if len(args) < 2:
                await update.effective_message.reply_text("Usage: /child add Name [Avatar]")
                return
            name = args[1]
            avatar = args[2] if len(args) > 2 else "\U0001f466"
            child = self.video_store.add_child(name, avatar)
            if not child:
                await update.effective_message.reply_text(f"A child named '{name}' already exists.")
                return
            default_limit = self.config.watch_limits.daily_limit_minutes
            self.video_store.set_child_setting(child["id"], "daily_limit_minutes", str(default_limit))
            await update.effective_message.reply_text(
                f"{avatar} <b>{_esc(name)}</b> profile created!\nDaily limit: {default_limit} minutes",
                parse_mode=ParseMode.HTML,
            )
            return

        # /child remove <name>
        if subcmd == "remove":
            if len(args) < 2:
                await update.effective_message.reply_text("Usage: /child remove Name")
                return
            name = args[1]
            child = self.video_store.get_child_by_name(name)
            if not child:
                await update.effective_message.reply_text(f"Child '{name}' not found.")
                return
            self.video_store.delete_avatar(child["id"])
            self.video_store.remove_child(child["id"])
            await update.effective_message.reply_text(
                f"{child.get('avatar', '')} <b>{_esc(child['name'])}</b> has been removed.",
                parse_mode=ParseMode.HTML,
            )
            return

        # /child rename <old> <new>
        if subcmd == "rename":
            if len(args) < 3:
                await update.effective_message.reply_text("Usage: /child rename OldName NewName")
                return
            old_name = args[1]
            new_name = args[2]
            child = self.video_store.get_child_by_name(old_name)
            if not child:
                await update.effective_message.reply_text(f"Child '{old_name}' not found.")
                return
            updated = self.video_store.update_child(child["id"], name=new_name)
            if not updated:
                await update.effective_message.reply_text(f"Failed. A child named '{new_name}' may already exist.")
                return
            await update.effective_message.reply_text(
                f"Renamed <b>{_esc(old_name)}</b> to <b>{_esc(new_name)}</b>",
                parse_mode=ParseMode.HTML,
            )
            return

        # /child <Name> — show single child summary
        child = self.video_store.get_child_by_name(args[0])
        if not child:
            await update.effective_message.reply_text(
                f"Child '{args[0]}' not found.\n\n"
                "Usage:\n"
                "/child \u2014 List all profiles\n"
                "/child add Name [Avatar]\n"
                "/child remove Name\n"
                "/child rename OldName NewName\n"
                "/child ChildName \u2014 Show profile summary"
            )
            return

        # Show detailed single-child summary
        cid = child["id"]
        tz = self.config.watch_limits.timezone
        today = get_today_str(tz)
        bounds = get_day_utc_bounds(today, tz)

        limit_str = self.video_store.get_child_setting(cid, "daily_limit_minutes", "")
        limit = int(limit_str) if limit_str else self.config.watch_limits.daily_limit_minutes
        used = self.video_store.get_daily_watch_minutes(cid, today, utc_bounds=bounds)
        remaining = max(0, limit - used)
        stats = self.video_store.get_stats(child_id=cid)
        channels = self.video_store.get_channels(cid, status="allowed")
        bar = _progress_bar(used / limit if limit > 0 else 0)

        lines = [
            f"{child.get('avatar', '')} <b>{_esc(child['name'])}</b>\n",
            f"<b>Time Today:</b> {used:.0f}/{limit} min {bar}",
            f"Remaining: {remaining:.0f} min\n",
            f"<b>Videos:</b> {stats['approved']} approved, {stats['pending']} pending, {stats['denied']} denied",
            f"<b>Channels:</b> {len(channels)} allowed",
        ]

        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.HTML
        )

    async def _cmd_addkid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        args = context.args or []
        if not args:
            await update.effective_message.reply_text(
                "Usage: /addkid Name [Avatar]\nExample: /addkid Alex or /addkid Sam 👧"
            )
            return

        name = args[0]
        avatar = args[1] if len(args) > 1 else "👦"

        child = self.video_store.add_child(name, avatar)
        if not child:
            await update.effective_message.reply_text(
                f"A child named '{name}' already exists."
            )
            return

        # Set default daily limit
        default_limit = self.config.watch_limits.daily_limit_minutes
        self.video_store.set_child_setting(child["id"], "daily_limit_minutes", str(default_limit))

        await update.effective_message.reply_text(
            f"{avatar} <b>{_esc(name)}</b> profile created!\n"
            f"Daily limit: {default_limit} minutes",
            parse_mode=ParseMode.HTML,
        )

    async def _cmd_editkid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        args = context.args or []
        if not args:
            await update.effective_message.reply_text(
                "Usage:\n"
                "/editkid CurrentName NewName [NewAvatar]\n"
                "/editkid CurrentName avatar NewAvatar\n\n"
                "Or send a photo with caption: avatar ChildName"
            )
            return

        current_name = args[0]
        child = self.video_store.get_child_by_name(current_name)
        if not child:
            await update.effective_message.reply_text(f"Child '{current_name}' not found.")
            return

        if len(args) == 1:
            await update.effective_message.reply_text(
                "Usage:\n"
                "/editkid CurrentName NewName [NewAvatar]\n"
                "/editkid CurrentName avatar NewAvatar"
            )
            return

        # /editkid Name avatar 👧
        if args[1].lower() == "avatar" and len(args) >= 3:
            new_avatar = args[2]
            updated = self.video_store.update_child(child["id"], avatar=new_avatar)
            if updated:
                await update.effective_message.reply_text(
                    f"Avatar for <b>{_esc(updated['name'])}</b> updated to {_esc(new_avatar)}",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await update.effective_message.reply_text("Failed to update avatar.")
            return

        # /editkid CurrentName NewName [NewAvatar]
        new_name = args[1]
        new_avatar = args[2] if len(args) > 2 else None
        updated = self.video_store.update_child(child["id"], name=new_name, avatar=new_avatar)
        if not updated:
            await update.effective_message.reply_text(
                f"Failed to update. A child named '{new_name}' may already exist."
            )
            return

        parts = [f"<b>{_esc(child['name'])}</b> renamed to <b>{_esc(updated['name'])}</b>"]
        if new_avatar:
            parts.append(f"Avatar: {_esc(new_avatar)}")
        await update.effective_message.reply_text(
            "\n".join(parts), parse_mode=ParseMode.HTML
        )

    async def _cmd_removekid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        args = context.args or []
        if not args:
            await update.effective_message.reply_text(
                "Usage: /removekid ChildName\n"
                "This permanently deletes the child and all their data."
            )
            return

        name = args[0]
        child = self.video_store.get_child_by_name(name)
        if not child:
            await update.effective_message.reply_text(f"Child '{name}' not found.")
            return

        child_id = child["id"]
        child_name = child["name"]
        avatar = child.get("avatar", "")

        # Delete avatar file if exists
        self.video_store.delete_avatar(child_id)
        # Delete child (cascades settings, access, watch_log)
        self.video_store.remove_child(child_id)

        await update.effective_message.reply_text(
            f"{avatar} <b>{_esc(child_name)}</b> has been removed.\n"
            "All watch history, settings, and video access data deleted.",
            parse_mode=ParseMode.HTML,
        )

    async def _handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo messages — used for setting photo avatars.

        Caption format: avatar ChildName
        """
        if not self._is_admin(update):
            return

        caption = (update.effective_message.caption or "").strip()
        if not caption.lower().startswith("avatar "):
            return  # Not an avatar upload, ignore

        child_name = caption[7:].strip()
        if not child_name:
            await update.effective_message.reply_text(
                "Send a photo with caption: avatar ChildName"
            )
            return

        child = self.video_store.get_child_by_name(child_name)
        if not child:
            await update.effective_message.reply_text(f"Child '{child_name}' not found.")
            return

        # Download the largest available photo
        photo = update.effective_message.photo[-1]  # Highest resolution
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()

        if self.video_store.save_avatar(child["id"], bytes(photo_bytes)):
            await update.effective_message.reply_text(
                f"Photo avatar set for <b>{_esc(child['name'])}</b>!",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.effective_message.reply_text("Failed to save avatar photo.")

    async def _cmd_pending(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        await self._show_pending_page(update.effective_message, page=0, edit=False)

    async def _show_pending_page(self, message, page: int = 0, edit: bool = True):
        """Display a page of pending video requests with action buttons."""
        pending = self.video_store.get_pending_requests()

        if not pending:
            text = "No pending requests."
            await self._send_or_edit(message, text, edit=edit)
            return

        total = len(pending)
        start = page * _PENDING_PAGE_SIZE
        page_items = pending[start:start + _PENDING_PAGE_SIZE]

        lines = [f"<b>Pending Requests ({total})</b>\n"]
        action_rows = []
        for i, item in enumerate(page_items, start=start + 1):
            child_id = item["child_id"]
            video_id = item["video_id"]
            child_name = item.get("child_name", "?")
            title = item.get("title", video_id)
            channel = item.get("channel_name", "?")
            dur = format_duration(item.get("duration"))
            lines.append(
                f"{i}. [{_esc(child_name)}] <b>{_esc(title)}</b>\n"
                f"  {_esc(channel)} • {dur}"
            )
            action_rows.append([
                InlineKeyboardButton(f"✓ Edu {i}", callback_data=f"pnd_edu:{child_id}:{page}:{video_id}"),
                InlineKeyboardButton(f"✓ Fun {i}", callback_data=f"pnd_fun:{child_id}:{page}:{video_id}"),
                InlineKeyboardButton(f"✗ {i}", callback_data=f"pnd_deny:{child_id}:{page}:{video_id}"),
            ])

        # Pagination buttons
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("< Prev", callback_data=f"pending_page:{page - 1}"))
        if start + _PENDING_PAGE_SIZE < total:
            nav.append(InlineKeyboardButton("Next >", callback_data=f"pending_page:{page + 1}"))

        rows = action_rows + ([nav] if nav else [])
        keyboard = InlineKeyboardMarkup(rows) if rows else None
        text = "\n".join(lines)
        await self._send_or_edit(message, text, keyboard=keyboard, edit=edit)

    async def _cmd_approved(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        args = context.args or []
        child_name = args[0] if args else None
        child = self._resolve_child(child_name)

        if child_name and not child:
            await update.effective_message.reply_text(f"Child '{child_name}' not found.")
            return

        if not child:
            children = self._all_children()
            if not children:
                await update.effective_message.reply_text("No child profiles yet.")
                return
            if len(children) > 1:
                names = ", ".join(c["name"] for c in children)
                await update.effective_message.reply_text(
                    f"Multiple children found. Specify a name: /approved [Name]\nChildren: {names}"
                )
                return
            child = children[0]

        await self._show_approved_page(update.effective_message, child["id"], page=0, edit=False)

    async def _show_approved_page(self, message, child_id: int, page: int = 0, edit: bool = True):
        """Display a page of approved videos for a child."""
        child = self.video_store.get_child(child_id)
        child_name = child["name"] if child else f"Child#{child_id}"

        offset = page * _APPROVED_PAGE_SIZE
        videos, total = self.video_store.get_approved_videos(
            child_id, offset=offset, limit=_APPROVED_PAGE_SIZE
        )

        if total == 0:
            text = f"No approved videos for {_esc(child_name)}."
            await self._send_or_edit(message, text, edit=edit)
            return

        lines = [f"<b>Approved for {_esc(child_name)} ({total})</b>\n"]
        revoke_buttons = []
        for i, v in enumerate(videos, start=offset + 1):
            title = v.get("title", v.get("video_id", "?"))
            channel = v.get("channel_name", "?")
            cat = v.get("effective_category", "")
            cat_tag = f" [{cat}]" if cat else ""
            lines.append(f"{i}. <b>{_esc(title)}</b>{cat_tag}\n   {_esc(channel)}")
            vid = v.get("video_id", "")
            revoke_buttons.append([InlineKeyboardButton(
                f"Revoke {i}",
                callback_data=f"rev:{child_id}:{page}:{vid}",
            )])

        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("< Prev", callback_data=f"approved_page:{child_id}:{page - 1}"))
        if offset + _APPROVED_PAGE_SIZE < total:
            nav_buttons.append(InlineKeyboardButton("Next >", callback_data=f"approved_page:{child_id}:{page + 1}"))

        rows = revoke_buttons + ([nav_buttons] if nav_buttons else [])
        keyboard = InlineKeyboardMarkup(rows) if rows else None
        text = "\n".join(lines)
        await self._send_or_edit(message, text, keyboard=keyboard, edit=edit)

    async def _cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        args = context.args or []
        child_name = args[0] if args else None

        if child_name:
            child = self._resolve_child(child_name)
            if not child:
                await update.effective_message.reply_text(f"Child '{child_name}' not found.")
                return
            stats = self.video_store.get_stats(child_id=child["id"])
            header = f"Stats for {_esc(child['name'])}"
            text = (
                f"<b>{header}</b>\n\n"
                f"Total requests: {stats['total']}\n"
                f"Approved: {stats['approved']}\n"
                f"Denied: {stats['denied']}\n"
                f"Pending: {stats['pending']}"
            )
        else:
            children = self._all_children()
            if len(children) > 1:
                # Combined summary across all children
                tz = self.config.watch_limits.timezone
                today = get_today_str(tz)
                bounds = get_day_utc_bounds(today, tz)

                lines = ["<b>Stats \u2014 All Children</b>\n"]
                for child in children:
                    cid = child["id"]
                    s = self.video_store.get_stats(child_id=cid)
                    used = self.video_store.get_daily_watch_minutes(cid, today, utc_bounds=bounds)
                    limit_str = self.video_store.get_child_setting(cid, "daily_limit_minutes", "")
                    limit = int(limit_str) if limit_str else self.config.watch_limits.daily_limit_minutes
                    bar = _progress_bar(used / limit if limit > 0 else 0)

                    lines.append(
                        f"{child.get('avatar', '')} <b>{_esc(child['name'])}</b>\n"
                        f"  Videos: {s['approved']} approved, {s['pending']} pending\n"
                        f"  Today: {used:.0f}/{limit} min {bar}"
                    )

                overall = self.video_store.get_stats()
                lines.append(f"\n<b>Overall:</b> {overall['total']} total, {overall['approved']} approved, {overall['pending']} pending")
                text = "\n".join(lines)
            else:
                stats = self.video_store.get_stats()
                header = "Overall Stats"
                text = (
                    f"<b>{header}</b>\n\n"
                    f"Total requests: {stats['total']}\n"
                    f"Approved: {stats['approved']}\n"
                    f"Denied: {stats['denied']}\n"
                    f"Pending: {stats['pending']}"
                )

        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)

    async def _cmd_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        args = context.args or []

        # Parse: /channel [ChildName] [subcommand] [args...]
        child, sub_args = self._parse_child_args(args)

        if not child:
            children = self._all_children()
            if not children:
                await update.effective_message.reply_text("No child profiles yet.")
                return
            if len(children) > 1:
                names = ", ".join(c["name"] for c in children)
                await update.effective_message.reply_text(
                    f"Specify a child: /channel [Name] [allow|block|unallow|unblock]\nChildren: {names}"
                )
                return
            child = children[0]
            sub_args = list(args)

        child_id = child["id"]
        child_name = child["name"]

        # /channel ChildName (no subcommand) -> list channels
        if not sub_args:
            await self._show_channel_page(update.effective_message, child_id, page=0, edit=False)
            return

        subcmd = sub_args[0].lower()

        # /channel [ChildName] starter — browse starter channels
        if subcmd == "starter":
            await self._show_starter_page(update.effective_message, child_id, page=0, edit=False)
            return

        # /channel [ChildName] allow <name> [category]
        if subcmd == "allow" and len(sub_args) >= 2:
            rest = sub_args[1:]
            if rest[-1].lower() in ("edu", "fun"):
                category = rest[-1].lower()
                name = " ".join(rest[:-1]) if len(rest) > 1 else rest[0]
            else:
                category = None
                name = " ".join(rest)
            self.video_store.add_channel(child_id, name, "allowed", category=category)
            cat_label = f" ({category})" if category else ""
            await update.effective_message.reply_text(
                f"Channel <b>{_esc(name)}</b> allowed for {_esc(child_name)}{cat_label}.",
                parse_mode=ParseMode.HTML,
            )

        # /channel [ChildName] block <name>
        elif subcmd == "block" and len(sub_args) >= 2:
            name = " ".join(sub_args[1:])
            self.video_store.add_channel(child_id, name, "blocked")
            await update.effective_message.reply_text(
                f"Channel <b>{_esc(name)}</b> blocked for {_esc(child_name)}.",
                parse_mode=ParseMode.HTML,
            )

        # /channel [ChildName] unallow <name>
        elif subcmd == "unallow" and len(sub_args) >= 2:
            name = " ".join(sub_args[1:])
            if self.video_store.remove_channel(child_id, name):
                await update.effective_message.reply_text(
                    f"Channel <b>{_esc(name)}</b> removed from {_esc(child_name)}'s allow list.",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await update.effective_message.reply_text(f"Channel '{name}' not found for {child_name}.")

        # /channel [ChildName] unblock <name>
        elif subcmd == "unblock" and len(sub_args) >= 2:
            name = " ".join(sub_args[1:])
            if self.video_store.remove_channel(child_id, name):
                await update.effective_message.reply_text(
                    f"Channel <b>{_esc(name)}</b> removed from {_esc(child_name)}'s block list.",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await update.effective_message.reply_text(f"Channel '{name}' not found for {child_name}.")

        else:
            await update.effective_message.reply_text(
                "Usage:\n"
                "/channel [ChildName] — List channels\n"
                "/channel [ChildName] allow Name [edu|fun]\n"
                "/channel [ChildName] block Name\n"
                "/channel [ChildName] unallow Name\n"
                "/channel [ChildName] unblock Name"
            )

    async def _show_channel_page(self, message, child_id: int, page: int = 0, edit: bool = True):
        """Display paginated channel list for a child."""
        child = self.video_store.get_child(child_id)
        child_name = child["name"] if child else f"Child#{child_id}"

        allowed = self.video_store.get_channels(child_id, status="allowed")
        blocked = self.video_store.get_channels(child_id, status="blocked")

        if not allowed and not blocked:
            text = f"No channels configured for {_esc(child_name)}. Use /channel {_esc(child_name)} allow or /channel {_esc(child_name)} block."
            await self._send_or_edit(message, text, edit=edit)
            return

        lines = []
        if allowed:
            lines.append(f"<b>Allowed Channels for {_esc(child_name)} ({len(allowed)})</b>")
            start = page * _CHANNEL_PAGE_SIZE
            for ch in allowed[start:start + _CHANNEL_PAGE_SIZE]:
                cat = ch.get("category", "")
                cat_tag = f" [{cat}]" if cat else ""
                lines.append(f"  + {_esc(ch['channel_name'])}{cat_tag}")

        if blocked:
            lines.append(f"\n<b>Blocked Channels for {_esc(child_name)} ({len(blocked)})</b>")
            for ch in blocked[:_CHANNEL_PAGE_SIZE]:
                lines.append(f"  - {_esc(ch['channel_name'])}")

        total = len(allowed)  # paginate allowed only
        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("< Prev", callback_data=f"chan_page:{child_id}:{page - 1}"))
        if (page + 1) * _CHANNEL_PAGE_SIZE < total:
            buttons.append(InlineKeyboardButton("Next >", callback_data=f"chan_page:{child_id}:{page + 1}"))

        keyboard = InlineKeyboardMarkup([buttons]) if buttons else None
        text = "\n".join(lines)
        await self._send_or_edit(message, text, keyboard=keyboard, edit=edit)

    def _load_starter_channels(self) -> dict:
        """Load starter channels from bundled YAML."""
        yaml_path = Path(__file__).resolve().parent.parent / "starter_channels.yaml"
        if not yaml_path.exists():
            return {}
        with open(yaml_path) as f:
            return yaml.safe_load(f) or {}

    async def _show_starter_page(self, message, child_id: int, page: int = 0, edit: bool = True):
        """Display paginated starter channels with import buttons."""
        child = self.video_store.get_child(child_id)
        child_name = child["name"] if child else f"Child#{child_id}"

        data = self._load_starter_channels()
        if not data:
            await self._send_or_edit(message, "No starter channels available.", edit=edit)
            return

        # Flatten all channels with category labels
        all_channels = []
        for category, channels_list in data.items():
            for ch in channels_list:
                all_channels.append({**ch, "category_key": category})

        # Get already-imported handles for this child
        existing = self.video_store.get_channels(child_id)
        imported_handles = {ch.get("handle", "").lower() for ch in existing if ch.get("handle")}

        total = len(all_channels)
        start = page * _STARTER_PAGE_SIZE
        page_items = all_channels[start:start + _STARTER_PAGE_SIZE]

        lines = [f"<b>Starter Channels for {_esc(child_name)}</b> ({start + 1}-{min(start + len(page_items), total)} of {total})\n"]

        buttons = []
        for ch in page_items:
            handle = ch.get("handle", "")
            name = ch.get("name", handle)
            cat = ch.get("category_key", "")
            age = ch.get("age_range", "")
            desc = ch.get("description", "")
            is_imported = handle.lower() in imported_handles

            mark = "\u2705 " if is_imported else ""
            lines.append(f"{mark}<b>{_esc(name)}</b> [{cat}]")
            if age:
                lines.append(f"  Ages {age}")
            if desc:
                lines.append(f"  <i>{_esc(desc)}</i>")
            lines.append("")

            if not is_imported:
                buttons.append([InlineKeyboardButton(
                    f"Import {name}",
                    callback_data=f"starter_import:{child_id}:{handle}",
                )])

        # Pagination nav
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("\u25c0 Back", callback_data=f"starter_page:{child_id}:{page - 1}"))
        if start + _STARTER_PAGE_SIZE < total:
            nav.append(InlineKeyboardButton("Next \u25b6", callback_data=f"starter_page:{child_id}:{page + 1}"))
        if nav:
            buttons.append(nav)

        keyboard = InlineKeyboardMarkup(buttons) if buttons else None
        text = "\n".join(lines)
        await self._send_or_edit(message, text, keyboard=keyboard, edit=edit)

    async def _import_starter_channel(self, query, child_id: int, handle: str):
        """Import a single starter channel for a child."""
        data = self._load_starter_channels()

        # Find the channel info
        info = None
        for category, channels_list in data.items():
            for ch in channels_list:
                if ch.get("handle", "").lower() == handle.lower():
                    info = {**ch, "category_key": category}
                    break
            if info:
                break

        if not info:
            await query.answer("Channel not found in starter list.")
            return

        cat_key = info.get("category_key", "fun")
        category = "edu" if cat_key in ("educational", "science") else "fun"
        name = info.get("name", handle)

        self.video_store.add_channel(
            child_id, name, "allowed",
            handle=info.get("handle"),
            category=category,
        )

        await query.answer(f"Imported {name}!")

        # Re-render the current page
        # Determine which page this channel was on
        all_channels = []
        for cat, cl in data.items():
            for c in cl:
                all_channels.append(c)

        idx = next((i for i, c in enumerate(all_channels) if c.get("handle", "").lower() == handle.lower()), 0)
        page = idx // _STARTER_PAGE_SIZE
        await self._show_starter_page(query.message, child_id, page)

    async def _cmd_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        args = context.args or []

        # Parse: /time [ChildName] [subcommand] [args...]
        child, sub_args = self._parse_child_args(args)

        if not child:
            children = self._all_children()
            if not children:
                await update.effective_message.reply_text("No child profiles yet.")
                return
            if len(children) > 1 and args and not sub_args:
                # First arg might be a subcommand, not a child name
                child = None
            elif len(children) == 1:
                child = children[0]
                sub_args = list(args)

        # /time (no subcommand) -> show status
        if not sub_args:
            if child:
                await self._show_time_status(update.effective_message, child)
            else:
                children = self._all_children()
                if len(children) > 1:
                    names = ", ".join(c["name"] for c in children)
                    await update.effective_message.reply_text(
                        f"Specify a child: /time [Name] [set|schedule|off]\nChildren: {names}"
                    )
                    return
                await self._show_time_status(update.effective_message, children[0])
            return

        subcmd = sub_args[0].lower()

        if not child:
            children = self._all_children()
            if len(children) == 1:
                child = children[0]
            else:
                names = ", ".join(c["name"] for c in children)
                await update.effective_message.reply_text(
                    f"Multiple children exist. Specify: /time ChildName {subcmd}\nChildren: {names}"
                )
                return

        cid = child["id"]
        cname = child["name"]

        # /time [Child] set <minutes>
        if subcmd == "set" and len(sub_args) >= 2:
            try:
                minutes = int(sub_args[1])
                if minutes < 0:
                    raise ValueError
            except ValueError:
                await update.effective_message.reply_text("Invalid minutes. Use a positive number.")
                return
            self.video_store.set_child_setting(cid, "daily_limit_minutes", str(minutes))
            await update.effective_message.reply_text(
                f"Daily limit for {_esc(cname)} set to <b>{minutes}</b> minutes.",
                parse_mode=ParseMode.HTML,
            )

        # /time [Child] off
        elif subcmd == "off":
            self.video_store.set_child_setting(cid, "daily_limit_minutes", "0")
            await update.effective_message.reply_text(
                f"Daily limit for {_esc(cname)} <b>disabled</b>.",
                parse_mode=ParseMode.HTML,
            )

        # /time [Child] schedule <start> <end>
        elif subcmd == "schedule" and len(sub_args) >= 3:
            start_raw = sub_args[1]
            end_raw = sub_args[2]

            if start_raw.lower() == "off":
                self.video_store.set_child_setting(cid, "schedule_start", "")
                self.video_store.set_child_setting(cid, "schedule_end", "")
                await update.effective_message.reply_text(
                    f"Schedule for {_esc(cname)} <b>disabled</b>.",
                    parse_mode=ParseMode.HTML,
                )
                return

            start = parse_time_input(start_raw)
            end = parse_time_input(end_raw)
            if not start or not end:
                await update.effective_message.reply_text(
                    "Invalid time format. Use: /time Name schedule 800 2000"
                )
                return

            self.video_store.set_child_setting(cid, "schedule_start", start)
            self.video_store.set_child_setting(cid, "schedule_end", end)
            await update.effective_message.reply_text(
                f"Schedule for {_esc(cname)}: <b>{format_time_12h(start)}</b> to <b>{format_time_12h(end)}</b>",
                parse_mode=ParseMode.HTML,
            )

        # /time [Child] <minutes> (shorthand for /time set)
        elif subcmd.isdigit():
            minutes = int(subcmd)
            self.video_store.set_child_setting(cid, "daily_limit_minutes", str(minutes))
            await update.effective_message.reply_text(
                f"Daily limit for {_esc(cname)} set to <b>{minutes}</b> minutes.",
                parse_mode=ParseMode.HTML,
            )

        else:
            await update.effective_message.reply_text(
                "Usage:\n"
                "/time [ChildName] — View time status\n"
                "/time [ChildName] set 90 — Set daily limit\n"
                "/time [ChildName] off — Disable limit\n"
                "/time [ChildName] schedule 800 2000 — Set schedule\n"
                "/time [ChildName] schedule off — Disable schedule"
            )

    async def _show_time_status(self, message, child: dict):
        """Display time usage status for a child."""
        cid = child["id"]
        cname = child["name"]
        tz = self.config.watch_limits.timezone

        limit_str = self.video_store.get_child_setting(cid, "daily_limit_minutes", "")
        limit = int(limit_str) if limit_str else self.config.watch_limits.daily_limit_minutes

        today = get_today_str(tz)
        bounds = get_day_utc_bounds(today, tz)
        used = self.video_store.get_daily_watch_minutes(cid, today, utc_bounds=bounds)

        # Check free day pass
        free_day = self.video_store.get_child_setting(cid, "free_day_date", "")
        is_free_day = free_day == today

        remaining = max(0, limit - used)

        bar = _progress_bar(used / limit if limit > 0 else 0)

        lines = [
            f"<b>Time Status — {_esc(cname)}</b>\n",
            f"Daily limit: {limit} min" + (" (off)" if limit == 0 else ""),
            f"Used today: {used:.0f} min",
            f"Remaining: {'unlimited' if is_free_day else f'{remaining:.0f} min'}",
            f"Progress: {bar}",
        ]

        if is_free_day:
            lines.append("\nFree day pass: <b>ACTIVE</b>")

        # Schedule
        sched_start = self.video_store.get_child_setting(cid, "schedule_start", "")
        sched_end = self.video_store.get_child_setting(cid, "schedule_end", "")
        if sched_start or sched_end:
            allowed, unlock = is_within_schedule(sched_start, sched_end, tz)
            start_fmt = format_time_12h(sched_start) if sched_start else "midnight"
            end_fmt = format_time_12h(sched_end) if sched_end else "midnight"
            status = "Active" if allowed else f"Locked (opens {unlock})"
            lines.append(f"\nSchedule: {start_fmt} — {end_fmt}")
            lines.append(f"Status: {status}")

        await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def _cmd_freeday(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Grant or revoke a free day pass (unlimited watch time today).

        /freeday [ChildName] — toggle free day for today
        /freeday [ChildName] off — revoke free day
        """
        if not await self._check_admin(update):
            return

        args = context.args or []
        child, sub_args = self._parse_child_args(args)

        if not child:
            children = self._all_children()
            if not children:
                await update.effective_message.reply_text("No child profiles yet.")
                return
            if len(children) > 1:
                names = ", ".join(c["name"] for c in children)
                await update.effective_message.reply_text(
                    f"Specify a child: /freeday [Name] [off]\nChildren: {names}"
                )
                return
            child = children[0]
            sub_args = list(args)

        cid = child["id"]
        cname = child["name"]
        tz = self.config.watch_limits.timezone
        today = get_today_str(tz)

        # /freeday [Child] off — revoke
        if sub_args and sub_args[0].lower() == "off":
            self.video_store.set_child_setting(cid, "free_day_date", "")
            await update.effective_message.reply_text(
                f"Free day pass <b>revoked</b> for {_esc(cname)}.",
                parse_mode=ParseMode.HTML,
            )
            return

        # Toggle: if already set for today, revoke; otherwise grant
        current = self.video_store.get_child_setting(cid, "free_day_date", "")
        if current == today:
            self.video_store.set_child_setting(cid, "free_day_date", "")
            await update.effective_message.reply_text(
                f"Free day pass <b>revoked</b> for {_esc(cname)}.",
                parse_mode=ParseMode.HTML,
            )
        else:
            self.video_store.set_child_setting(cid, "free_day_date", today)
            await update.effective_message.reply_text(
                f"Free day pass <b>granted</b> for {_esc(cname)} today! No time limits.",
                parse_mode=ParseMode.HTML,
            )

    async def _cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        args = context.args or []
        child_name = args[0] if args else None
        child = self._resolve_child(child_name)

        if child_name and not child:
            children = self._all_children()
            if len(children) == 1:
                child = children[0]
            else:
                await update.effective_message.reply_text(f"Child '{child_name}' not found.")
                return

        if not child:
            children = self._all_children()
            if not children:
                await update.effective_message.reply_text("No child profiles yet.")
                return
            if len(children) > 1:
                # Combined watch activity for all children
                tz = self.config.watch_limits.timezone
                today = get_today_str(tz)
                bounds = get_day_utc_bounds(today, tz)

                lines = ["<b>Watch Activity \u2014 All Children (Today)</b>\n"]
                any_activity = False
                for c in children:
                    breakdown = self.video_store.get_daily_watch_breakdown(c["id"], today, utc_bounds=bounds)
                    total_min = sum(v["minutes"] for v in breakdown)
                    lines.append(f"{c.get('avatar', '')} <b>{_esc(c['name'])}</b>: {total_min:.1f} min")
                    if breakdown:
                        any_activity = True
                        for v in breakdown[:3]:  # Top 3 videos per child
                            title = v.get("title", v.get("video_id", "?"))
                            lines.append(f"  \u2022 {_esc(title)} \u2014 {v['minutes']:.1f} min")
                        if len(breakdown) > 3:
                            lines.append(f"  <i>...and {len(breakdown) - 3} more</i>")
                    else:
                        lines.append("  <i>No activity</i>")
                    lines.append("")

                if not any_activity:
                    await update.effective_message.reply_text("No watch activity today.")
                    return

                await update.effective_message.reply_text(
                    "\n".join(lines), parse_mode=ParseMode.HTML
                )
                return
            child = children[0]

        tz = self.config.watch_limits.timezone
        today = get_today_str(tz)
        bounds = get_day_utc_bounds(today, tz)

        breakdown = self.video_store.get_daily_watch_breakdown(child["id"], today, utc_bounds=bounds)
        total_min = sum(v["minutes"] for v in breakdown)

        if not breakdown:
            await update.effective_message.reply_text(
                f"No watch activity today for {_esc(child['name'])}.",
                parse_mode=ParseMode.HTML,
            )
            return

        lines = [f"<b>Watch Activity \u2014 {_esc(child['name'])} (Today)</b>\n"]
        lines.append(f"Total: {total_min:.1f} min\n")

        for v in breakdown:
            title = v.get("title", v.get("video_id", "?"))
            mins = v["minutes"]
            channel = v.get("channel_name", "?")
            lines.append(f"  <b>{_esc(title)}</b> \u2014 {mins:.1f} min\n  {_esc(channel)}")

        await update.effective_message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.HTML
        )

    async def _cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manage word filters."""
        if not await self._check_admin(update):
            return

        args = context.args or []

        # /search (no args) -> list word filters
        if not args:
            words = self.video_store.get_word_filters()
            if not words:
                await update.effective_message.reply_text(
                    "No word filters configured.\n/search add word — Add a filter"
                )
                return
            word_list = ", ".join(words)
            await update.effective_message.reply_text(
                f"<b>Word Filters ({len(words)})</b>\n{_esc(word_list)}\n\n"
                "/search add word — Add\n/search remove word — Remove",
                parse_mode=ParseMode.HTML,
            )
            return

        subcmd = args[0].lower()

        if subcmd == "add" and len(args) >= 2:
            word = " ".join(args[1:])
            if self.video_store.add_word_filter(word):
                await update.effective_message.reply_text(f"Filter added: '{word}'")
            else:
                await update.effective_message.reply_text(f"Filter '{word}' already exists.")

        elif subcmd == "remove" and len(args) >= 2:
            word = " ".join(args[1:])
            if self.video_store.remove_word_filter(word):
                await update.effective_message.reply_text(f"Filter removed: '{word}'")
            else:
                await update.effective_message.reply_text(f"Filter '{word}' not found.")

        else:
            await update.effective_message.reply_text(
                "Usage:\n"
                "/search — List word filters\n"
                "/search add word — Add filter\n"
                "/search remove word — Remove filter"
            )

    # ── Helpers ────────────────────────────────────────────────────

    async def _send_or_edit(self, message, text: str, keyboard=None, edit: bool = True):
        """Send a new message or edit an existing one."""
        kwargs = {"parse_mode": ParseMode.HTML}
        if keyboard:
            kwargs["reply_markup"] = keyboard
        if edit:
            try:
                await message.edit_text(text, **kwargs)
                return
            except Exception:
                pass
        await message.reply_text(text, **kwargs)

    def _parse_child_args(self, args: list) -> tuple[Optional[dict], list]:
        """Parse args where the first arg may be a child name.

        Returns (child, remaining_args). If first arg is a child name,
        child is set and remaining_args excludes it. Otherwise, tries
        to resolve single-child default.
        """
        if not args:
            return (None, [])

        # Try first arg as child name
        child = self.video_store.get_child_by_name(args[0])
        if child:
            return (child, args[1:])

        # First arg is not a child name — check if single child default works
        children = self.video_store.get_children()
        if len(children) == 1:
            return (children[0], list(args))

        return (None, list(args))
