"""대시보드·비용 화면용 집계. 환산 불가/데이터 없음은 0이 아닌 None 으로 돌려준다."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.fx import SOURCE_LABELS
from app.models import CostRecord, Device, Subscription, UsageEvent, UsageImport, UsageSnapshot, UserSettings
from app.money import convert, monthly_equivalent


def fx_info(settings: UserSettings) -> dict | None:
    """화면에 표시할 환율 정보 (원 통화·환산 통화와 함께 적용 환율·기준일·출처를 노출)."""
    if settings.fx_usd_krw is None:
        return None
    return {
        "usd_krw": settings.fx_usd_krw,
        "rate_date": settings.fx_rate_date,
        "mode": settings.fx_mode,
        "source": settings.fx_source,
        "source_label": SOURCE_LABELS.get(settings.fx_source or "", settings.fx_source),
        "updated_at": settings.fx_updated_at,
    }


# 에이전트는 값이 바뀌면 1분 안에, 바뀌지 않아도 5분마다 신호를 보낸다
ONLINE_WINDOW = timedelta(minutes=7)
MONTH_METRIC = "tokens_month"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def is_online(device: Device, now: datetime | None = None) -> bool:
    if device.revoked_at is not None or device.last_seen_at is None:
        return False
    return (now or datetime.now(UTC)) - _aware(device.last_seen_at) <= ONLINE_WINDOW


def device_month_usage(db: Session, user_id: uuid.UUID, settings: UserSettings) -> dict[str, list[dict]]:
    """서비스별 → 기기별 이번 달 누계. 기기마다 하나의 행만 있으므로 그대로 합산하면 된다."""
    month_start = local_today(settings).replace(day=1)
    rows = db.execute(
        select(UsageSnapshot, Device)
        .join(Device, UsageSnapshot.device_id == Device.id)
        .where(
            UsageSnapshot.user_id == user_id,
            UsageSnapshot.metric_code == MONTH_METRIC,
            UsageSnapshot.period_start == month_start,
        )
        .order_by(Device.name)
    ).all()
    now = datetime.now(UTC)
    result: dict[str, list[dict]] = defaultdict(list)
    for snap, device in rows:
        result[snap.service_id].append(
            {
                "device_id": device.id,
                "name": device.name,
                "used_value": snap.used_value,
                "captured_at": snap.captured_at,
                "online": is_online(device, now),
                "revoked": device.revoked_at is not None,
                "snapshot": snap,
            }
        )
    return dict(result)


TOKEN_FIELDS = ("input", "output", "cache_creation", "cache_read")


def month_bounds_utc(settings: UserSettings, start: date) -> tuple[datetime, datetime]:
    """현지 시간 기준 한 달 [시작, 다음 달 시작) 을 UTC 로."""
    tz = ZoneInfo(settings.timezone)
    nxt = date(start.year + start.month // 12, start.month % 12 + 1, 1)
    return (
        datetime.combine(start, datetime.min.time(), tz).astimezone(UTC),
        datetime.combine(nxt, datetime.min.time(), tz).astimezone(UTC),
    )


def _event_rows(db: Session, user_id: uuid.UUID, since: datetime, until: datetime, service_id: str | None = None):
    query = select(UsageEvent).where(
        UsageEvent.user_id == user_id, UsageEvent.occurred_at >= since, UsageEvent.occurred_at < until
    )
    if service_id:
        query = query.where(UsageEvent.service_id == service_id)
    return db.scalars(query)


def _local_month(dt: datetime, tz: ZoneInfo) -> str:
    return _aware(dt).astimezone(tz).strftime("%Y-%m")


def event_month_usage(db: Session, user_id: uuid.UUID, settings: UserSettings) -> dict[str, dict]:
    """서비스별 이번 달 CSV 업로드 토큰 합계와 마지막 업로드 시각."""
    since, until = month_bounds_utc(settings, local_today(settings).replace(day=1))
    totals: dict[str, dict] = {}
    for e in _event_rows(db, user_id, since, until):
        t = totals.setdefault(e.service_id, {"used_value": 0, "breakdown": dict.fromkeys(TOKEN_FIELDS, 0)})
        t["used_value"] += e.total_tokens
        b = t["breakdown"]
        b["input"] += e.input_tokens
        b["output"] += e.output_tokens
        b["cache_creation"] += e.cache_creation_tokens
        b["cache_read"] += e.cache_read_tokens
    if totals:
        last_upload = dict(
            db.execute(
                select(UsageImport.service_id, func.max(UsageImport.uploaded_at))
                .where(UsageImport.user_id == user_id, UsageImport.service_id.in_(totals))
                .group_by(UsageImport.service_id)
            ).all()
        )
        for service_id, t in totals.items():
            t["captured_at"] = last_upload.get(service_id)
    return totals


def token_months(db: Session, user_id: uuid.UUID, settings: UserSettings, service_id: str, months: int = 12) -> list[dict]:
    """최근 N개월 토큰 합계 (기기 에이전트 + CSV 업로드). 데이터가 있는 달만, 최근 달부터."""
    tz = ZoneInfo(settings.timezone)
    end_period = current_period(settings)
    periods = [shift_period(end_period, -i) for i in range(months)]
    first = date.fromisoformat(periods[-1] + "-01")
    rows: dict[str, dict] = {}

    def bucket(period: str) -> dict:
        return rows.setdefault(
            period, {"period": period, "total": 0, **dict.fromkeys(TOKEN_FIELDS, 0), "devices": 0, "csv": 0}
        )

    device_rows = db.scalars(
        select(UsageSnapshot).where(
            UsageSnapshot.user_id == user_id,
            UsageSnapshot.service_id == service_id,
            UsageSnapshot.device_id.is_not(None),
            UsageSnapshot.metric_code == MONTH_METRIC,
            UsageSnapshot.period_start >= first,
        )
    )
    for snap in device_rows:
        period = snap.period_start.strftime("%Y-%m")
        if period not in periods:
            continue
        b = bucket(period)
        value = int(snap.used_value or 0)
        b["total"] += value
        b["devices"] += value
        for key in TOKEN_FIELDS:
            b[key] += int((snap.raw or {}).get(key, 0))

    since, _ = month_bounds_utc(settings, first)
    for e in _event_rows(db, user_id, since, datetime.now(UTC) + timedelta(days=1), service_id):
        period = _local_month(e.occurred_at, tz)
        if period not in periods:
            continue
        b = bucket(period)
        b["total"] += e.total_tokens
        b["csv"] += e.total_tokens
        b["input"] += e.input_tokens
        b["output"] += e.output_tokens
        b["cache_creation"] += e.cache_creation_tokens
        b["cache_read"] += e.cache_read_tokens
    return [rows[p] for p in periods if p in rows]


def local_today(settings: UserSettings) -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def current_period(settings: UserSettings) -> str:
    return local_today(settings).strftime("%Y-%m")


def shift_period(period: str, months: int) -> str:
    year, month = map(int, period.split("-"))
    index = year * 12 + (month - 1) + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


@dataclass
class Converted:
    """표시 통화 합계. missing=True 면 환율이 없어 일부 금액이 합계에서 빠졌다는 뜻이다."""

    total: Decimal | None
    missing: bool


def _sum(amounts: list[Decimal | None]) -> Converted:
    known = [a for a in amounts if a is not None]
    missing = len(known) != len(amounts)
    return Converted(total=sum(known, Decimal(0)) if known else None, missing=missing)


def convert_cost(record: CostRecord, settings: UserSettings) -> Decimal | None:
    rate = record.exchange_rate or settings.fx_usd_krw
    return convert(record.amount, record.currency, settings.currency, rate)


def active_subscriptions(db: Session, user_id: uuid.UUID) -> list[Subscription]:
    return list(
        db.scalars(
            select(Subscription)
            .where(Subscription.user_id == user_id, Subscription.is_active.is_(True))
            .order_by(Subscription.service_id)
        )
    )


def subscription_monthly(sub: Subscription, settings: UserSettings) -> Decimal | None:
    return convert(monthly_equivalent(sub.price, sub.billing_cycle), sub.currency, settings.currency, settings.fx_usd_krw)


def subscription_total(subs: list[Subscription], settings: UserSettings) -> Converted:
    return _sum([subscription_monthly(s, settings) for s in subs])


def api_costs_for_period(db: Session, user_id: uuid.UUID, period: str) -> list[CostRecord]:
    return list(
        db.scalars(
            select(CostRecord).where(
                CostRecord.user_id == user_id,
                CostRecord.billing_period == period,
                CostRecord.cost_type == "api_usage",
            )
        )
    )


def api_cost_by_service(records: list[CostRecord], settings: UserSettings) -> dict[str, Converted]:
    grouped: dict[str, list[Decimal | None]] = defaultdict(list)
    for r in records:
        grouped[r.service_id].append(convert_cost(r, settings))
    return {service_id: _sum(amounts) for service_id, amounts in grouped.items()}


def daily_api_costs(db: Session, user_id: uuid.UUID, settings: UserSettings, days: int) -> list[dict]:
    """최근 N일 일별 API 비용 (일 단위 버킷만 — 수동 월 입력은 제외)."""
    end = local_today(settings)
    start = end - timedelta(days=days - 1)
    records = db.scalars(
        select(CostRecord).where(
            CostRecord.user_id == user_id,
            CostRecord.cost_type == "api_usage",
            CostRecord.granularity == "day",
            CostRecord.cost_date >= start,
            CostRecord.cost_date <= end,
        )
    ).all()
    by_day: dict[date, list[Decimal | None]] = defaultdict(list)
    for r in records:
        by_day[r.cost_date].append(convert_cost(r, settings))
    result = []
    for i in range(days):
        day = start + timedelta(days=i)
        converted = _sum(by_day.get(day, []))
        result.append({"date": day, "amount": converted.total, "conversion_missing": converted.missing})
    return result


def monthly_api_trend(db: Session, user_id: uuid.UUID, settings: UserSettings, months: int) -> list[dict]:
    end_period = current_period(settings)
    periods = [shift_period(end_period, -i) for i in reversed(range(months))]
    records = db.scalars(
        select(CostRecord).where(
            CostRecord.user_id == user_id,
            CostRecord.cost_type == "api_usage",
            CostRecord.billing_period.in_(periods),
        )
    ).all()
    by_period: dict[str, list[CostRecord]] = defaultdict(list)
    for r in records:
        by_period[r.billing_period].append(r)
    trend = []
    for period in periods:
        per_service = api_cost_by_service(by_period.get(period, []), settings)
        trend.append(
            {
                "period": period,
                "by_service": {k: v.total for k, v in per_service.items()},
                "conversion_missing": any(v.missing for v in per_service.values()),
            }
        )
    return trend
