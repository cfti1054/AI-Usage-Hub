from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.models import AiService, UsageSnapshot
from app.schemas import ManualEntryIn, ManualEntryOut
from app.sync import upsert_cost

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.post("/manual", response_model=ManualEntryOut, status_code=status.HTTP_201_CREATED)
def manual_entry(body: ManualEntryIn, db: DbSession, user: CurrentUser) -> ManualEntryOut:
    if db.get(AiService, body.service_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "존재하지 않는 서비스입니다")
    if body.usage is None and body.cost is None:
        raise HTTPException(422, "usage 또는 cost 중 하나는 필요합니다")

    snapshot = None
    if body.usage is not None:
        snapshot = UsageSnapshot(
            user_id=user.id,
            service_id=body.service_id,
            source_type=body.source_type,
            status="ok" if body.usage.used_value is not None else "unavailable",
            **body.usage.model_dump(),
        )
        db.add(snapshot)

    cost = None
    if body.cost is not None:
        year, month = map(int, body.cost.billing_period.split("-"))
        cost = upsert_cost(
            db,
            user_id=user.id,
            service_id=body.service_id,
            source_type=body.source_type,
            cost_type="api_usage",
            granularity="month",
            cost_date=date(year, month, 1),
            amount=body.cost.amount,
            currency=body.cost.currency,
        )
        cost.exchange_rate = body.cost.exchange_rate

    db.commit()
    return ManualEntryOut(snapshot_id=snapshot.id if snapshot else None, cost_record_id=cost.id if cost else None)
