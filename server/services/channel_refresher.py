"""Background task that periodically imports new videos from allowed channels.

Runs as an asyncio task alongside the FastAPI server.  Reuses the existing
InvidiousClient.get_channel_videos() and VideoStore.bulk_import_channel_videos()
so duplicate videos are silently skipped (INSERT OR IGNORE).
"""

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.telegram_bot import TelegramBot
    from config import Config
    from data.video_store import VideoStore
    from invidious.client import InvidiousClient

logger = logging.getLogger(__name__)

# Seconds to sleep between individual channel fetches to avoid hammering Invidious
_STAGGER_SECONDS = 2


async def channel_refresh_loop(
    store: "VideoStore",
    inv_client: "InvidiousClient",
    bot: "TelegramBot | None",
    cfg: "Config",
) -> None:
    """Run forever, refreshing allowed channels on a configurable cadence."""
    interval_hours = cfg.invidious.channel_refresh_hours
    interval_seconds = interval_hours * 3600

    logger.info(
        "Channel refresh loop started (every %d hours)", interval_hours
    )

    # One-time backfill of published_at for existing videos
    await _backfill_published_at(store, inv_client)

    while True:
        try:
            total_imported = await _refresh_all_channels(
                store, inv_client, bot, interval_hours
            )
            if total_imported > 0:
                logger.info(
                    "Channel refresh complete: %d new videos imported",
                    total_imported,
                )
            else:
                logger.info("Channel refresh complete: no new videos")
        except Exception:
            logger.exception("Unexpected error in channel refresh loop")

        await asyncio.sleep(interval_seconds)


async def _refresh_all_channels(
    store: "VideoStore",
    inv_client: "InvidiousClient",
    bot: "TelegramBot | None",
    interval_hours: int,
) -> int:
    """Sweep all allowed channels due for refresh. Returns total new videos."""
    channels = store.get_all_channels_due_for_refresh(interval_hours)
    if not channels:
        logger.debug("No channels due for refresh")
        return 0

    all_children = store.get_children()
    all_child_ids = [c["id"] for c in all_children]
    if not all_child_ids:
        logger.debug("No child profiles — skipping refresh")
        return 0

    logger.info("Refreshing %d channel(s)", len(channels))

    total_imported = 0
    summary_lines: list[str] = []

    for ch in channels:
        ch_name = ch["channel_name"]
        ch_id = ch["channel_id"]
        category = ch.get("category") or "fun"

        try:
            videos = await inv_client.get_channel_videos(ch_id)
            imported = store.bulk_import_channel_videos(
                videos, category, all_child_ids
            )
            store.update_all_channels_refreshed_at(ch_name)

            if imported > 0:
                total_imported += imported
                summary_lines.append(f"  {ch_name}: +{imported}")
                logger.info(
                    "Channel %s: imported %d new videos", ch_name, imported
                )
            else:
                logger.debug("Channel %s: no new videos", ch_name)

        except Exception:
            logger.warning(
                "Failed to refresh channel %s (skipping)", ch_name,
                exc_info=True,
            )

        # Stagger requests to avoid overloading Invidious
        await asyncio.sleep(_STAGGER_SECONDS)

    # Send Telegram summary if there were new imports
    if total_imported > 0 and bot:
        await _notify_telegram(bot, total_imported, summary_lines)

    return total_imported


async def _backfill_published_at(
    store: "VideoStore",
    inv_client: "InvidiousClient",
) -> None:
    """Backfill published_at for videos that are missing it."""
    video_ids = store.get_videos_missing_published_at(limit=200)
    if not video_ids:
        return

    logger.info("Backfilling published_at for %d videos", len(video_ids))
    filled = 0
    for vid in video_ids:
        try:
            meta = await inv_client.get_video(vid)
            if meta and meta.get("published"):
                store.update_published_at(vid, meta["published"])
                filled += 1
        except Exception:
            logger.debug("Failed to backfill published_at for %s", vid)
        await asyncio.sleep(0.5)

    logger.info("Backfilled published_at for %d/%d videos", filled, len(video_ids))


async def _notify_telegram(
    bot: "TelegramBot",
    total: int,
    lines: list[str],
) -> None:
    """Send a summary message to the admin via Telegram."""
    try:
        details = "\n".join(lines)
        text = (
            f"<b>Channel refresh</b>: {total} new video(s) imported.\n"
            f"<pre>{details}</pre>"
        )
        await bot._app.bot.send_message(
            chat_id=bot.admin_chat_id,
            text=text,
            parse_mode="HTML",
        )
    except Exception:
        logger.warning("Failed to send refresh summary to Telegram", exc_info=True)
