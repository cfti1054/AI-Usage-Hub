from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import select

from app import reports, scheduler
from app.deps import CurrentUser, DbSession, get_user_settings
from app.models import AiService, ServiceCredential, SyncJob, UsageSnapshot
from app.schemas import SnapshotOut, SubscriptionOut, SyncJobOut

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _usage_rate(snap: UsageSnapshot | None) -> float | None:
    if snap is None or snap.status != "ok" or snap.used_value is None or not snap.limit_value:
        return None
    return float(snap.used_value / snap.limit_value * 100)


def _data_state(service: AiService, snap: UsageSnapshot | None, job: SyncJob | None) -> str:
    """카드 상태. 데이터를 못 가져온 경우를 0%와 구분하기 위한 값이다."""
    if not service.enabled:
        return "disabled"
    if job is not None and job.status == "failed" and (
        snap is None or _aware(job.started_at) > _aware(snap.captured_at)
    ):
        return "error"
    if snap is None:
        return "no_data"
    if snap.status == "unavailable":
        return "unavailable"
    return "ok"


@router.get("/summary")
def summary(db: DbSession, user: CurrentUser) -> dict:
    settings = get_user_settings(db, user)
    period = reports.current_period(settings)
    services = db.scalars(select(AiService).order_by(AiService.created_at, AiService.id)).all()

    subs = reports.active_subscriptions(db, user.id)
    subs_by_service = {s.service_id: s for s in subs}
    sub_total = reports.subscription_total(subs, settings)

    api_by_service = reports.api_cost_by_service(reports.api_costs_for_period(db, user.id, period), settings)
    api_totals = [v.total for v in api_by_service.values() if v.total is not None]
    api_total = sum(api_totals, Decimal(0)) if api_totals else None
    api_missing = any(v.missing for v in api_by_service.values())

    stale_after = timedelta(minutes=settings.sync_interval_minutes * 2)
    now = datetime.now(UTC)
    device_usage = reports.device_month_usage(db, user.id, settings)
    cards = []
    for service in services:
        devices = device_usage.get(service.id, [])
        if devices:
            # 기기 에이전트 값이 있으면 기기별 이번 달 누계를 합산해 하나의 사용량으로 보여준다
            latest = max(devices, key=lambda d: _aware(d["captured_at"]))["snapshot"]
            snap = latest
            usage = SnapshotOut.model_validate(latest).model_copy(
                update={"used_value": sum((d["used_value"] or 0 for d in devices), Decimal(0))}
            )
        else:
            # 기기 값(지난달 누계·일별 행 포함)은 제외하고 수동 입력·API 값 중 최신 1건
            snap = db.scalar(
                select(UsageSnapshot)
                .where(
                    UsageSnapshot.user_id == user.id,
                    UsageSnapshot.service_id == service.id,
                    UsageSnapshot.device_id.is_(None),
                )
                .order_by(UsageSnapshot.captured_at.desc())
                .limit(1)
            )
            usage = SnapshotOut.model_validate(snap) if snap else None
        job = db.scalar(
            select(SyncJob).where(SyncJob.service_id == service.id).order_by(SyncJob.started_at.desc()).limit(1)
        )
        sub = subs_by_service.get(service.id)
        api_cost = api_by_service.get(service.id)
        state = _data_state(service, snap, job)
        cards.append(
            {
                "id": service.id,
                "name": service.name,
                "provider": service.provider,
                "collection_method": service.collection_method,
                "enabled": service.enabled,
                "has_credential": db.get(ServiceCredential, service.id) is not None,
                "subscription": SubscriptionOut.model_validate(sub) if sub else None,
                "subscription_monthly": reports.subscription_monthly(sub, settings) if sub else None,
                "usage": usage,
                "usage_rate": _usage_rate(snap) if not devices else None,
                "devices": [
                    {k: d[k] for k in ("device_id", "name", "used_value", "captured_at", "online", "revoked")}
                    for d in devices
                ],
                "month_api_cost": api_cost.total if api_cost else None,
                "last_sync": SyncJobOut.model_validate(job) if job else None,
                "data_state": state,
                # 자동 수집 서비스인데 수집 주기 2배 이상 갱신이 없으면 오래된 데이터로 표시
                "stale": bool(
                    service.collection_method == "api" and snap is not None and now - _aware(snap.captured_at) > stale_after
                ),
            }
        )

    enabled_cards = [c for c in cards if c["enabled"]]
    rates = [c["usage_rate"] for c in enabled_cards if c["usage_rate"] is not None]
    last_synced = max((c["last_sync"].finished_at for c in cards if c["last_sync"] and c["last_sync"].finished_at), default=None)
    return {
        "period": period,
        "currency": settings.currency,
        "fx": reports.fx_info(settings),
        "subscription_total": sub_total.total,
        "api_cost_total": api_total,
        "conversion_missing": sub_total.missing or api_missing,
        "services_connected": sum(1 for c in enabled_cards if c["data_state"] == "ok"),
        "services_total": len(enabled_cards),
        "avg_usage_rate": sum(rates) / len(rates) if rates else None,
        "services": cards,
        "daily_api_costs": reports.daily_api_costs(db, user.id, settings, days=7),
        "last_synced_at": last_synced,
        "next_sync_at": scheduler.next_run_time(),
    }
