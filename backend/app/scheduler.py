"""APScheduler — FastAPI 프로세스 내부에서 주기 수집을 실행한다.

주의: Railway 서비스 레플리카는 1개로 유지해야 중복 수집이 발생하지 않는다.
"""

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app import fx
from app.db import get_sessionmaker
from app.models import AiService, User
from app.sync import run_sync

logger = logging.getLogger(__name__)

JOB_ID = "sync-all"
FX_JOB_ID = "fx-refresh"
_scheduler: BackgroundScheduler | None = None


def sync_all_services() -> None:
    with get_sessionmaker()() as db:
        user = db.scalar(select(User).order_by(User.created_at))
        if user is None:
            return
        services = db.scalars(
            select(AiService).where(AiService.enabled.is_(True), AiService.connector.is_not(None))
        ).all()
        for service in services:
            job = run_sync(db, service, user.id, trigger="schedule")
            logger.info("scheduled sync %s → %s", service.id, job.status)


def refresh_fx() -> None:
    with get_sessionmaker()() as db:
        try:
            count = fx.refresh_auto_settings(db)
            logger.info("fx refreshed for %d settings", count)
        except fx.FxError as exc:  # 실패 시 기존 환율 유지
            logger.warning("%s", exc)


def start(interval_minutes: int, fx_refresh_hours: int) -> None:
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(sync_all_services, "interval", minutes=interval_minutes, id=JOB_ID, max_instances=1, coalesce=True)
    # 기동 직후 1회 + 이후 주기적으로 환율 갱신
    _scheduler.add_job(
        refresh_fx, "interval", hours=fx_refresh_hours, id=FX_JOB_ID,
        next_run_time=datetime.now(UTC), max_instances=1, coalesce=True,
    )
    _scheduler.start()


def reschedule(interval_minutes: int) -> None:
    if _scheduler is not None:
        _scheduler.reschedule_job(JOB_ID, trigger="interval", minutes=interval_minutes)


def next_run_time() -> datetime | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    return job.next_run_time if job else None


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
