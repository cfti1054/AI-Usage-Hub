"""커넥터 실행 → 정규화 데이터 저장 → sync_jobs 기록.

수집 실패 시 기존 데이터는 그대로 두고 실패 이력만 남긴다 (기획서 10장 오류 처리 원칙).
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors import get_connector
from app.connectors.base import ConnectorContext, ConnectorError, ConnectorResult
from app.credentials import get_secret
from app.models import AiService, CostRecord, SyncJob, UsageSnapshot
from app.security import mask_secrets

logger = logging.getLogger(__name__)

# 비용 데이터는 늦게 확정되는 경우가 있어 최근 며칠을 다시 받아 upsert 한다
LOOKBACK_DAYS = 35


class SyncNotSupported(Exception):
    pass


def run_sync(db: Session, service: AiService, user_id: uuid.UUID, trigger: str = "manual") -> SyncJob:
    connector = get_connector(service.connector)
    if connector is None:
        raise SyncNotSupported(f"{service.name}: 자동 수집 커넥터가 없습니다 (수동 입력 서비스)")

    job = SyncJob(
        service_id=service.id,
        started_at=datetime.now(UTC),
        status="running",
        source_type=connector.source_type,
        trigger=trigger,
    )
    db.add(job)
    db.commit()

    secret = get_secret(db, service.id)
    try:
        if connector.requires_secret and not secret:
            raise ConnectorError("API 키가 설정되지 않았습니다")
        today = date.today()
        ctx = ConnectorContext(
            service_id=service.id, secret=secret, since=today - timedelta(days=LOOKBACK_DAYS), until=today
        )
        result = connector.fetch(ctx)
        job.records_count = _persist(db, service.id, user_id, connector.source_type, result)
        job.status = "success"
    except Exception as exc:  # 커넥터 오류는 모두 sync_jobs 로 남기고 삼킨다
        db.rollback()
        if not isinstance(exc, ConnectorError):
            logger.exception("sync failed for %s", service.id)
        job.status = "failed"
        job.error_message = mask_secrets(str(exc), [secret or ""])[:1000]
    job.finished_at = datetime.now(UTC)
    db.add(job)
    db.commit()
    return job


def _persist(db: Session, service_id: str, user_id: uuid.UUID, source_type: str, result: ConnectorResult) -> int:
    for s in result.snapshots:
        db.add(
            UsageSnapshot(
                user_id=user_id,
                service_id=service_id,
                metric_code=s.metric_code,
                used_value=s.used_value if s.status == "ok" else None,
                limit_value=s.limit_value,
                unit=s.unit,
                status=s.status,
                period_start=s.period_start,
                period_end=s.period_end,
                resets_at=s.resets_at,
                source_type=source_type,
                raw=s.raw,
            )
        )
    for c in result.costs:
        upsert_cost(
            db,
            user_id=user_id,
            service_id=service_id,
            source_type=source_type,
            cost_type=c.cost_type,
            granularity=c.granularity,
            cost_date=c.cost_date,
            amount=c.amount,
            currency=c.currency,
        )
    db.commit()
    return len(result.snapshots) + len(result.costs)


def upsert_cost(db: Session, *, user_id, service_id, source_type, cost_type, granularity, cost_date, amount, currency) -> CostRecord:
    # DB 방언과 무관하게 동작하도록 조회 후 갱신한다 (단일 사용자·저빈도 쓰기)
    record = db.scalar(
        select(CostRecord).where(
            CostRecord.user_id == user_id,
            CostRecord.service_id == service_id,
            CostRecord.cost_type == cost_type,
            CostRecord.source_type == source_type,
            CostRecord.granularity == granularity,
            CostRecord.cost_date == cost_date,
        )
    )
    if record is None:
        record = CostRecord(
            user_id=user_id,
            service_id=service_id,
            cost_type=cost_type,
            source_type=source_type,
            granularity=granularity,
            cost_date=cost_date,
        )
        db.add(record)
    record.amount = amount
    record.currency = currency
    record.billing_period = cost_date.strftime("%Y-%m")
    return record
