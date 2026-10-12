from decimal import Decimal

from fastapi import APIRouter, Query
from sqlalchemy import select

from app import reports
from app.deps import CurrentUser, DbSession, get_user_settings
from app.models import AiService

router = APIRouter(prefix="/api/costs", tags=["costs"])


@router.get("")
def costs(
    db: DbSession,
    user: CurrentUser,
    period: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
) -> dict:
    """월별 구독료와 API 종량제 비용을 분리해 돌려준다."""
    settings = get_user_settings(db, user)
    period = period or reports.current_period(settings)
    names = {row.id: row.name for row in db.execute(select(AiService.id, AiService.name))}

    subs = reports.active_subscriptions(db, user.id)
    sub_total = reports.subscription_total(subs, settings)

    records = reports.api_costs_for_period(db, user.id, period)
    api_by_service = reports.api_cost_by_service(records, settings)
    original: dict[str, dict[str, Decimal]] = {}
    for r in records:
        per_currency = original.setdefault(r.service_id, {})
        per_currency[r.currency] = per_currency.get(r.currency, Decimal(0)) + r.amount
    api_totals = [v.total for v in api_by_service.values() if v.total is not None]

    return {
        "period": period,
        "currency": settings.currency,
        "fx": reports.fx_info(settings),
        "subscriptions": [
            {
                "service_id": s.service_id,
                "service_name": names.get(s.service_id, s.service_id),
                "plan_name": s.plan_name,
                "billing_cycle": s.billing_cycle,
                "price": s.price,
                "currency": s.currency,
                "monthly_converted": reports.subscription_monthly(s, settings),
            }
            for s in subs
        ],
        "subscription_total": sub_total.total,
        "api_costs": [
            {
                "service_id": service_id,
                "service_name": names.get(service_id, service_id),
                "original": original.get(service_id, {}),
                "converted": converted.total,
                "conversion_missing": converted.missing,
            }
            for service_id, converted in sorted(api_by_service.items())
        ],
        "api_cost_total": sum(api_totals, Decimal(0)) if api_totals else None,
        "conversion_missing": sub_total.missing or any(v.missing for v in api_by_service.values()),
    }


@router.get("/trend")
def cost_trend(db: DbSession, user: CurrentUser, months: int = Query(12, ge=1, le=36)) -> dict:
    settings = get_user_settings(db, user)
    return {"currency": settings.currency, "months": reports.monthly_api_trend(db, user.id, settings, months)}
