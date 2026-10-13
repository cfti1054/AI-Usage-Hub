import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Query
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
def summary(
    db: DbSession,
    user: CurrentUser,
    period: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> dict:
    """대시보드 요약. period(YYYY-MM)를 주면 그 달 기준, 없으면 이번 달.

    구독료는 월별 이력이 없어 어느 달을 보든 현재 등록된 활성 구독 기준이다.
    """
    settings = get_user_settings(db, user)
    current = reports.current_period(settings)
    period = period or current
    is_current = period == current
    month_start = date.fromisoformat(period + "-01")
    month_end = month_start.replace(day=calendar.monthrange(month_start.year, month_start.month)[1])
    since, until = reports.month_bounds_utc(settings, month_start)
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
    device_usage = reports.device_month_usage(db, user.id, settings, month_start)
    csv_usage = reports.event_month_usage(db, user.id, settings, month_start)
    cards = []
    for service in services:
        # 해당 월 토큰 출처: 기기 에이전트(기기별 누계) + CSV 업로드(요청별 합계)
        sources = [
            {k: d[k] for k in ("device_id", "name", "used_value", "captured_at", "online", "revoked")} | {"kind": "device"}
            for d in device_usage.get(service.id, [])
        ]
        csv = csv_usage.get(service.id)
        if csv:
            sources.append(
                {
                    "kind": "csv",
                    "device_id": None,
                    "name": "CSV 업로드",
                    "used_value": Decimal(csv["used_value"]),
                    "captured_at": csv["captured_at"] or now,
                    "online": False,
                    "revoked": False,
                }
            )
        if sources:
            # 출처별 이번 달 값을 합산해 하나의 사용량으로 보여준다
            usage = SnapshotOut(
                id=0,
                metric_code=reports.MONTH_METRIC,
                used_value=sum((Decimal(s["used_value"] or 0) for s in sources), Decimal(0)),
                limit_value=None,
                unit="tokens",
                status="ok",
                period_start=month_start,
                period_end=None,
                resets_at=None,
                source_type="cli" if any(s["kind"] == "device" for s in sources) else "manual",
                captured_at=max(_aware(s["captured_at"]) for s in sources),
            )
            snap = usage
        else:
            # 기기 값(월 누계·일별 행)은 제외하고 수동 입력·API 값 중 해당 월 말까지의 최신 1건.
            # 지난달을 볼 때는 그 달 안에 기록된 값만 쓴다
            conditions = [
                UsageSnapshot.user_id == user.id,
                UsageSnapshot.service_id == service.id,
                UsageSnapshot.device_id.is_(None),
                UsageSnapshot.captured_at < until,
            ]
            if not is_current:
                conditions.append(UsageSnapshot.captured_at >= since)
            snap = db.scalar(
                select(UsageSnapshot)
                .where(*conditions)
                .order_by(UsageSnapshot.captured_at.desc())
                .limit(1)
            )
            usage = SnapshotOut.model_validate(snap) if snap else None
        # 수집 실패·오래된 데이터 표시는 이번 달을 볼 때만 의미가 있다
        job = (
            db.scalar(
                select(SyncJob).where(SyncJob.service_id == service.id).order_by(SyncJob.started_at.desc()).limit(1)
            )
            if is_current
            else None
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
                "usage_rate": _usage_rate(snap) if not sources else None,
                # 이름은 기존 호환을 위해 devices 로 유지. kind 가 'device' 또는 'csv'
                "devices": sources,
                "month_api_cost": api_cost.total if api_cost else None,
                "last_sync": SyncJobOut.model_validate(job) if job else None,
                "data_state": state,
                # 자동 수집 서비스인데 수집 주기 2배 이상 갱신이 없으면 오래된 데이터로 표시
                "stale": bool(
                    is_current
                    and service.collection_method == "api"
                    and snap is not None and now - _aware(snap.captured_at) > stale_after
                ),
            }
        )

    enabled_cards = [c for c in cards if c["enabled"]]
    rates = [c["usage_rate"] for c in enabled_cards if c["usage_rate"] is not None]
    last_synced = max((c["last_sync"].finished_at for c in cards if c["last_sync"] and c["last_sync"].finished_at), default=None)
    return {
        "period": period,
        "current_period": current,
        "is_current_month": is_current,
        "currency": settings.currency,
        "fx": reports.fx_info(settings),
        "subscription_total": sub_total.total,
        "api_cost_total": api_total,
        "conversion_missing": sub_total.missing or api_missing,
        "services_connected": sum(1 for c in enabled_cards if c["data_state"] == "ok"),
        "services_total": len(enabled_cards),
        "avg_usage_rate": sum(rates) / len(rates) if rates else None,
        "services": cards,
        # 이번 달: 최근 7일, 다른 달: 그 달 1일~말일
        "daily_api_costs": (
            reports.daily_api_costs(db, user.id, settings, days=7)
            if is_current
            else reports.daily_api_costs(db, user.id, settings, days=month_end.day, end=month_end)
        ),
        "last_synced_at": last_synced,
        "next_sync_at": scheduler.next_run_time() if is_current else None,
    }
