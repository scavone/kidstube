"""Main orchestrator — runs FastAPI server + Telegram bot.

The Telegram bot runs as a background task alongside the FastAPI server.
Both share the same VideoStore instance for data consistency.
"""

import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from config import load_config
from data.video_store import VideoStore
from invidious.client import InvidiousClient
from api import routes as api_routes
from bot.telegram_bot import TelegramBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app(cfg=None) -> FastAPI:
    """Build and configure the FastAPI application."""
    if cfg is None:
        cfg = load_config()

    # Initialize data layer
    store = VideoStore(cfg.database.path)

    # Initialize Invidious client
    inv_client = InvidiousClient(base_url=cfg.invidious.base_url)

    # Initialize Telegram bot
    bot = None
    if cfg.telegram.bot_token:
        bot = TelegramBot(
            bot_token=cfg.telegram.bot_token,
            admin_chat_id=cfg.telegram.admin_chat_id,
            video_store=store,
            config=cfg,
        )

    # Wire up API routes with bot notification callback
    notify_cb = bot.notify_new_request if bot else None
    api_routes.setup(store, inv_client, cfg, notify_cb=notify_cb)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        if bot:
            await bot.start()
        logger.info("%s server initialized", cfg.app_name)
        yield
        # Shutdown
        if bot:
            await bot.stop()
        store.close()
        logger.info("%s server shutting down", cfg.app_name)

    app = FastAPI(title=cfg.app_name, lifespan=lifespan)
    app.state.api_key = cfg.api_key

    app.include_router(api_routes.router)

    return app


def main():
    cfg = load_config()
    logger.info("Starting %s server on %s:%d", cfg.app_name, cfg.web.host, cfg.web.port)
    app = create_app(cfg)
    uvicorn.run(app, host=cfg.web.host, port=cfg.web.port)


if __name__ == "__main__":
    main()
