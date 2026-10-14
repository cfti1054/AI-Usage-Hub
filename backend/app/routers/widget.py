"""휴대폰 위젯용 API.

- /api/widget-tokens: 위젯 토큰 발급·목록·폐기 (대시보드 로그인 필요)
- /api/widget/summary: 이번 달 요약 (위젯 토큰 X-Widget-Token 으로 조회만 가능)

위젯 토큰은 요약 조회 외에는 아무것도 할 수 없다. 숫자는 대시보드와 같은 계산(dashboard.summary)을 쓴다.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import User, WidgetToken
from app.routers import dashboard
from app.schemas import WidgetTokenCreate, WidgetTokenCreated, WidgetTokenOut
from app.security import hash_device_token, new_widget_token

router = APIRouter(tags=["widget"])

SERVICE_COLORS = {"claude-code": "#E07A55", "codex": "#1DB98B", "cursor": "#F2B33D", "gemini-cli": "#4285F4"}
DEFAULT_COLOR = "#8A93A3"


# --- 토큰 관리 (로그인 사용자) ---

@router.get("/api/widget-tokens", response_model=list[WidgetTokenOut])
def list_widget_tokens(db: DbSession, user: CurrentUser) -> list[WidgetToken]:
    return list(
        db.scalars(select(WidgetToken).where(WidgetToken.user_id == user.id).order_by(WidgetToken.created_at, WidgetToken.id))
    )


@router.post("/api/widget-tokens", response_model=WidgetTokenCreated, status_code=status.HTTP_201_CREATED)
def create_widget_token(body: WidgetTokenCreate, db: DbSession, user: CurrentUser) -> WidgetTokenCreated:
    if db.scalar(select(WidgetToken).where(WidgetToken.user_id == user.id, WidgetToken.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "같은 이름의 위젯 토큰이 이미 있습니다")
    token = new_widget_token()
    record = WidgetToken(user_id=user.id, name=body.name, token_hash=hash_device_token(token))
    db.add(record)
    db.commit()
    return WidgetTokenCreated(widget_token=WidgetTokenOut.model_validate(record), token=token)


@router.post("/api/widget-tokens/{token_id}/revoke", response_model=WidgetTokenOut)
def revoke_widget_token(token_id: int, db: DbSession, user: CurrentUser) -> WidgetToken:
    record = db.get(WidgetToken, token_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "위젯 토큰을 찾을 수 없습니다")
    if record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        db.commit()
    return record


# --- 위젯 조회 (위젯 토큰) ---

def widget_user(db: DbSession, x_widget_token: Annotated[str | None, Header()] = None) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "위젯 토큰이 없거나 폐기되었습니다")
    if not x_widget_token:
        raise unauthorized
    record = db.scalar(select(WidgetToken).where(WidgetToken.token_hash == hash_device_token(x_widget_token)))
    if record is None or record.revoked_at is not None:
        raise unauthorized
    record.last_used_at = datetime.now(UTC)
    db.commit()
    user = db.get(User, record.user_id)
    if user is None:
        raise unauthorized
    return user


def _num(value) -> float | None:
    return None if value is None else float(value)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@router.get("/api/widget/summary")
def widget_summary(db: DbSession, user: Annotated[User, Depends(widget_user)]) -> dict:
    """위젯 한 장에 필요한 이번 달 요약. 값을 모르면 0 이 아니라 null 이다."""
    data = dashboard.summary(db=db, user=user, period=None)

    services = []
    for card in data["services"]:
        sources = card["devices"]
        if not card["enabled"] or not sources or card["usage"] is None:
            continue
        device_count = sum(1 for s in sources if s["kind"] == "device")
        meta = [f"기기 {device_count}대"] if device_count else []
        if any(s["kind"] == "csv" for s in sources):
            meta.append("CSV")
        services.append(
            {
                "id": card["id"],
                "name": card["name"],
                "color": SERVICE_COLORS.get(card["id"], DEFAULT_COLOR),
                "tokens": int(card["usage"].used_value or 0),
                "source": " · ".join(meta),
                "online": any(s["online"] for s in sources),
                "updated_at": _aware(card["usage"].captured_at),
            }
        )
    services.sort(key=lambda s: s["tokens"], reverse=True)
    tokens_total = sum(s["tokens"] for s in services) if services else None
    for s in services:
        s["share"] = round(s["tokens"] / tokens_total, 4) if tokens_total else None

    sub, api = data["subscription_total"], data["api_cost_total"]
    spend = None if sub is None and api is None else (sub or Decimal(0)) + (api or Decimal(0))
    period = data["period"]
    return {
        "period": period,
        "period_label": f"{int(period[5:])}월",
        "currency": data["currency"],
        "spend_total": _num(spend),
        "subscription_total": _num(sub),
        "api_cost_total": _num(api),
        "conversion_missing": data["conversion_missing"],
        "tokens_total": tokens_total,
        "services": services,
        "daily_api_costs": [{"date": d["date"], "amount": _num(d["amount"])} for d in data["daily_api_costs"]],
        "updated_at": max((s["updated_at"] for s in services), default=None),
        "generated_at": datetime.now(UTC),
    }
