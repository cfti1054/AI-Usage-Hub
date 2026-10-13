"""PC 에이전트 전용 API. 사용자 JWT 대신 기기 토큰(X-Device-Token 헤더)으로 인증한다."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select

from app.deps import DbSession
from app.models import AiService, Device, UsageSnapshot
from app.schemas import AgentUsageIn
from app.security import hash_device_token

router = APIRouter(prefix="/api/agent", tags=["agent"])


def current_device(db: DbSession, x_device_token: Annotated[str | None, Header()] = None) -> Device:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "기기 토큰이 없거나 폐기되었습니다")
    if not x_device_token:
        raise unauthorized
    device = db.scalar(select(Device).where(Device.token_hash == hash_device_token(x_device_token)))
    if device is None or device.revoked_at is not None:
        raise unauthorized
    return device


CurrentDevice = Annotated[Device, Depends(current_device)]


@router.post("/usage")
def upload_usage(body: AgentUsageIn, db: DbSession, device: CurrentDevice) -> dict:
    """기기의 기간별 누계를 덮어쓴다. 같은 값을 여러 번 보내도 행이 늘지 않는다."""
    service_ids = {s.service_id for s in body.snapshots}
    known = set(db.scalars(select(AiService.id).where(AiService.id.in_(service_ids))))
    unknown = service_ids - known
    if unknown:
        raise HTTPException(422, f"존재하지 않는 서비스: {', '.join(sorted(unknown))}")

    now = datetime.now(UTC)
    for s in body.snapshots:
        row = db.scalar(
            select(UsageSnapshot).where(
                UsageSnapshot.device_id == device.id,
                UsageSnapshot.service_id == s.service_id,
                UsageSnapshot.metric_code == s.metric_code,
                UsageSnapshot.period_start == s.period_start,
            )
        )
        if row is None:
            row = UsageSnapshot(
                user_id=device.user_id,
                device_id=device.id,
                service_id=s.service_id,
                metric_code=s.metric_code,
                period_start=s.period_start,
                source_type="cli",
            )
            db.add(row)
        row.used_value = s.used_value
        row.unit = s.unit
        row.period_end = s.period_end
        row.status = "ok"
        row.raw = s.raw
        row.captured_at = now
    device.last_seen_at = now
    db.commit()
    return {"saved": len(body.snapshots)}


@router.post("/heartbeat")
def heartbeat(db: DbSession, device: CurrentDevice) -> dict:
    device.last_seen_at = datetime.now(UTC)
    db.commit()
    return {"ok": True, "device": device.name}
