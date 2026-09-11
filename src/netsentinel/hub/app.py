"""FastAPI application factory for the hub."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..config import get_settings
from ..db import init_db
from .alerts import deliver_pending, prune_old_rows
from .routes_api import router as api_router
from .routes_dashboard import router as dashboard_router

log = logging.getLogger("netsentinel.hub")
_HERE = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    init_db()
    log.info("hub starting (v%s), db=%s", __version__, settings.db_path)

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(deliver_pending, "interval", seconds=30, id="deliver", max_instances=1)
    scheduler.add_job(prune_old_rows, "interval", hours=6, id="prune", max_instances=1)
    scheduler.start()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        log.info("hub stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="NetSentinel Hub",
        version=__version__,
        summary="Aggregator API + dashboard for NetSentinel sensors.",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    app.include_router(dashboard_router)
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    return app


app = create_app()
