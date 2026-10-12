from fastapi import APIRouter, Query
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import SyncJob
from app.schemas import SyncJobOut

router = APIRouter(prefix="/api/sync-jobs", tags=["sync"])


@router.get("", response_model=list[SyncJobOut])
def list_sync_jobs(
    db: DbSession,
    _: CurrentUser,
    service_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[SyncJob]:
    query = select(SyncJob).order_by(SyncJob.started_at.desc()).limit(limit)
    if service_id:
        query = query.where(SyncJob.service_id == service_id)
    if status:
        query = query.where(SyncJob.status == status)
    return list(db.scalars(query))
