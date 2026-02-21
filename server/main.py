"""Main orchestrator — runs FastAPI server.

Telegram bot integration is added in Phase 3.
"""

import logging
import uvicorn
from fastapi import FastAPI

from config import load_config
from data.video_store import VideoStore
from invidious.client import InvidiousClient
from api import routes as api_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app(cfg=None) -> FastAPI:
    """Build and configure the FastAPI application."""
    if cfg is None:
        cfg = load_config()

    app = FastAPI(title=cfg.app_name)
    app.state.api_key = cfg.api_key

    # Initialize data layer
    store = VideoStore(cfg.database.path)

    # Initialize Invidious client
    inv_client = InvidiousClient(base_url=cfg.invidious.base_url)

    # Wire up API routes
    api_routes.setup(store, inv_client, cfg)
    app.include_router(api_routes.router)

    @app.on_event("shutdown")
    async def shutdown():
        store.close()
        logger.info("%s server shutting down", cfg.app_name)

    logger.info("%s server initialized", cfg.app_name)
    return app


def main():
    cfg = load_config()
    logger.info("Starting %s server on %s:%d", cfg.app_name, cfg.web.host, cfg.web.port)
    app = create_app(cfg)
    uvicorn.run(app, host=cfg.web.host, port=cfg.web.port)


if __name__ == "__main__":
    main()
