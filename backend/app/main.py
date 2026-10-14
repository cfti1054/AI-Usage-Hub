import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select, text

from app import scheduler
from app.config import get_settings
from app.db import get_sessionmaker
from app.deps import DbSession
from app.models import UserSettings
from app.routers import agent, auth, costs, dashboard, devices, imports, services, settings, subscriptions, sync_jobs, usage, widget

logging.basicConfig(level=logging.INFO)


def _sync_interval() -> int:
    with get_sessionmaker()() as db:
        interval = db.scalar(select(UserSettings.sync_interval_minutes).limit(1))
    return interval or 60


@asynccontextmanager
async def lifespan(_: FastAPI):
    config = get_settings()
    if config.scheduler_enabled:
        scheduler.start(_sync_interval(), config.fx_refresh_hours)
    yield
    scheduler.shutdown()


app = FastAPI(title="AI Usage Hub API", version="0.1.0", lifespan=lifespan)

for r in (auth, dashboard, services, subscriptions, usage, costs, sync_jobs, settings, devices, agent, imports, widget):
    app.include_router(r.router)


@app.get("/health")
def health(db: DbSession) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
