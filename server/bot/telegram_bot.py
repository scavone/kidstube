"""Telegram bot for parental controls — multi-child support.

Adapted from BrainRotGuard's single-child bot to support multiple children.
Callback data pattern: action:childId:videoId (child context embedded).
Commands accept optional child name; default to only child if single.
"""

import asyncio
import logging
from io import BytesIO
from typing import Optional, Callable, Awaitable

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
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
    ):
        self.bot_token = bot_token
        self.admin_chat_id = int(admin_chat_id) if admin_chat_id else 0
        self.video_store = video_store
        self.config = config
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
            CommandHandler("addkid", self._cmd_addkid),
            CommandHandler("pending", self._cmd_pending),
            CommandHandler("approved", self._cmd_approved),
            CommandHandler("stats", self._cmd_stats),
            CommandHandler("channel", self._cmd_channel),
            CommandHandler("time", self._cmd_time),
            CommandHandler("watch", self._cmd_watch),
            CommandHandler("search", self._cmd_search),
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
        if action == "chan_page" and len(parts) >= 2:
            page = int(parts[1])
            await self._show_channel_page(query.message, page)
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
                self.video_store.add_channel(ch_name, "allowed", channel_id=ch_id, category=category)
                # Auto-approve this video for the requesting child
                self.video_store.update_video_status(child_id, video_id, "approved")
                self._set_video_category(video_id, category)
                label = "Educational" if category == "edu" else "Entertainment"
                await query.edit_message_caption(
                    caption=(
                        f"Channel <b>{_esc(ch_name)}</b> allowed ({label}).\n"
                        f"Video approved for {_esc(child_name)}."
                    ),
                    parse_mode=ParseMode.HTML,
                )

        elif action == "blockchan":
            if video:
                ch_name = video["channel_name"]
                ch_id = video.get("channel_id")
                self.video_store.add_channel(ch_name, "blocked", channel_id=ch_id)
                self.video_store.update_video_status(child_id, video_id, "denied")
                await query.edit_message_caption(
                    caption=(
                        f"Channel <b>{_esc(ch_name)}</b> blocked.\n"
                        f"Video denied for {_esc(child_name)}."
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
            "/kids — List child profiles\n"
            "/addkid Name Avatar — Add a child profile\n"
            "/pending — View pending video requests\n"
            "/approved [ChildName] — Approved videos\n"
            "/stats [ChildName] — Video statistics\n"
            "/channel — Manage channel allow/block lists\n"
            "/time [ChildName] — View/set time limits\n"
            "/watch [ChildName] — Watch activity today\n"
            "/search — Manage word filters\n"
            "/help — Show this message\n\n"
            "<i>Child name can be omitted if only one child exists.</i>"
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

    async def _cmd_pending(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        await self._show_pending_page(update.effective_message, page=0, edit=False)

    async def _show_pending_page(self, message, page: int = 0, edit: bool = True):
        """Display a page of pending video requests."""
        pending = self.video_store.get_pending_requests()

        if not pending:
            text = "No pending requests."
            await self._send_or_edit(message, text, edit=edit)
            return

        total = len(pending)
        start = page * _PENDING_PAGE_SIZE
        page_items = pending[start:start + _PENDING_PAGE_SIZE]

        lines = [f"<b>Pending Requests ({total})</b>\n"]
        for item in page_items:
            child_name = item.get("child_name", "?")
            title = item.get("title", item["video_id"])
            channel = item.get("channel_name", "?")
            dur = format_duration(item.get("duration"))
            lines.append(
                f"[{_esc(child_name)}] <b>{_esc(title)}</b>\n"
                f"  {_esc(channel)} • {dur}"
            )

        # Pagination buttons
        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("< Prev", callback_data=f"pending_page:{page - 1}"))
        if start + _PENDING_PAGE_SIZE < total:
            buttons.append(InlineKeyboardButton("Next >", callback_data=f"pending_page:{page + 1}"))

        keyboard = InlineKeyboardMarkup([buttons]) if buttons else None
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
        for i, v in enumerate(videos, start=offset + 1):
            title = v.get("title", v.get("video_id", "?"))
            channel = v.get("channel_name", "?")
            cat = v.get("effective_category", "")
            cat_tag = f" [{cat}]" if cat else ""
            lines.append(f"{i}. <b>{_esc(title)}</b>{cat_tag}\n   {_esc(channel)}")

        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("< Prev", callback_data=f"approved_page:{child_id}:{page - 1}"))
        if offset + _APPROVED_PAGE_SIZE < total:
            buttons.append(InlineKeyboardButton("Next >", callback_data=f"approved_page:{child_id}:{page + 1}"))

        keyboard = InlineKeyboardMarkup([buttons]) if buttons else None
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

        # /channel (no args) -> list channels
        if not args:
            await self._show_channel_page(update.effective_message, page=0, edit=False)
            return

        subcmd = args[0].lower()

        # /channel allow <name> [category]
        if subcmd == "allow" and len(args) >= 2:
            name = args[1]
            category = args[2].lower() if len(args) > 2 and args[2].lower() in ("edu", "fun") else None
            self.video_store.add_channel(name, "allowed", category=category)
            cat_label = f" ({category})" if category else ""
            await update.effective_message.reply_text(
                f"Channel <b>{_esc(name)}</b> added to allow list{cat_label}.",
                parse_mode=ParseMode.HTML,
            )

        # /channel block <name>
        elif subcmd == "block" and len(args) >= 2:
            name = args[1]
            self.video_store.add_channel(name, "blocked")
            await update.effective_message.reply_text(
                f"Channel <b>{_esc(name)}</b> added to block list.",
                parse_mode=ParseMode.HTML,
            )

        # /channel unallow <name>
        elif subcmd == "unallow" and len(args) >= 2:
            name = " ".join(args[1:])
            if self.video_store.remove_channel(name):
                await update.effective_message.reply_text(
                    f"Channel <b>{_esc(name)}</b> removed from allow list.",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await update.effective_message.reply_text(f"Channel '{name}' not found.")

        # /channel unblock <name>
        elif subcmd == "unblock" and len(args) >= 2:
            name = " ".join(args[1:])
            if self.video_store.remove_channel(name):
                await update.effective_message.reply_text(
                    f"Channel <b>{_esc(name)}</b> removed from block list.",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await update.effective_message.reply_text(f"Channel '{name}' not found.")

        else:
            await update.effective_message.reply_text(
                "Usage:\n"
                "/channel — List channels\n"
                "/channel allow Name [edu|fun]\n"
                "/channel block Name\n"
                "/channel unallow Name\n"
                "/channel unblock Name"
            )

    async def _show_channel_page(self, message, page: int = 0, edit: bool = True):
        """Display paginated channel list."""
        allowed = self.video_store.get_channels(status="allowed")
        blocked = self.video_store.get_channels(status="blocked")

        if not allowed and not blocked:
            text = "No channels configured. Use /channel allow or /channel block."
            await self._send_or_edit(message, text, edit=edit)
            return

        lines = []
        if allowed:
            lines.append(f"<b>Allowed Channels ({len(allowed)})</b>")
            start = page * _CHANNEL_PAGE_SIZE
            for ch in allowed[start:start + _CHANNEL_PAGE_SIZE]:
                cat = ch.get("category", "")
                cat_tag = f" [{cat}]" if cat else ""
                lines.append(f"  + {_esc(ch['channel_name'])}{cat_tag}")

        if blocked:
            lines.append(f"\n<b>Blocked Channels ({len(blocked)})</b>")
            for ch in blocked[:_CHANNEL_PAGE_SIZE]:
                lines.append(f"  - {_esc(ch['channel_name'])}")

        total = len(allowed)  # paginate allowed only
        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("< Prev", callback_data=f"chan_page:{page - 1}"))
        if (page + 1) * _CHANNEL_PAGE_SIZE < total:
            buttons.append(InlineKeyboardButton("Next >", callback_data=f"chan_page:{page + 1}"))

        keyboard = InlineKeyboardMarkup([buttons]) if buttons else None
        text = "\n".join(lines)
        await self._send_or_edit(message, text, keyboard=keyboard, edit=edit)

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
        remaining = max(0, limit - used)

        bar = _progress_bar(used / limit if limit > 0 else 0)

        lines = [
            f"<b>Time Status — {_esc(cname)}</b>\n",
            f"Daily limit: {limit} min" + (" (off)" if limit == 0 else ""),
            f"Used today: {used:.0f} min",
            f"Remaining: {remaining:.0f} min",
            f"Progress: {bar}",
        ]

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

    async def _cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self._check_admin(update):
            return

        args = context.args or []
        child_name = args[0] if args else None
        child = self._resolve_child(child_name)

        if child_name and not child:
            # Maybe the arg is a child name that doesn't exist
            # Try treating it as not a child name (only child, arg is something else)
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
                names = ", ".join(c["name"] for c in children)
                await update.effective_message.reply_text(
                    f"Specify a child: /watch [Name]\nChildren: {names}"
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

        lines = [f"<b>Watch Activity — {_esc(child['name'])} (Today)</b>\n"]
        lines.append(f"Total: {total_min:.1f} min\n")

        for v in breakdown:
            title = v.get("title", v.get("video_id", "?"))
            mins = v["minutes"]
            channel = v.get("channel_name", "?")
            lines.append(f"  <b>{_esc(title)}</b> — {mins:.1f} min\n  {_esc(channel)}")

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
