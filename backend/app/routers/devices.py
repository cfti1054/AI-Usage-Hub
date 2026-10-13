from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app import reports
from app.deps import CurrentUser, DbSession, get_user_settings
from app.models import Device
from app.schemas import DeviceCreate, DeviceCreated, DeviceOut
from app.security import hash_device_token, new_device_token

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _to_out(device: Device, usage: dict[str, dict[int, object]] | None = None) -> DeviceOut:
    out = DeviceOut.model_validate(device)
    out.online = reports.is_online(device)
    if usage:
        out.month_usage = {sid: per_device[device.id] for sid, per_device in usage.items() if device.id in per_device}
    return out


@router.get("", response_model=list[DeviceOut])
def list_devices(db: DbSession, user: CurrentUser) -> list[DeviceOut]:
    settings = get_user_settings(db, user)
    by_service = reports.device_month_usage(db, user.id, settings)
    usage = {sid: {e["device_id"]: e["used_value"] for e in entries} for sid, entries in by_service.items()}
    devices = db.scalars(select(Device).where(Device.user_id == user.id).order_by(Device.created_at, Device.id))
    return [_to_out(d, usage) for d in devices]


@router.post("", response_model=DeviceCreated, status_code=status.HTTP_201_CREATED)
def create_device(body: DeviceCreate, db: DbSession, user: CurrentUser) -> DeviceCreated:
    exists = db.scalar(select(Device).where(Device.user_id == user.id, Device.name == body.name))
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "같은 이름의 기기가 이미 있습니다")
    token = new_device_token()
    device = Device(user_id=user.id, name=body.name, token_hash=hash_device_token(token))
    db.add(device)
    db.commit()
    return DeviceCreated(device=_to_out(device), token=token)


def _get_own(db: DbSession, user: CurrentUser, device_id: int) -> Device:
    device = db.get(Device, device_id)
    if device is None or device.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "기기를 찾을 수 없습니다")
    return device


@router.post("/{device_id}/rotate-token", response_model=DeviceCreated)
def rotate_device_token(device_id: int, db: DbSession, user: CurrentUser) -> DeviceCreated:
    """새 토큰을 발급한다. 기존 토큰은 즉시 무효가 되고, 기기와 사용량 기록은 그대로 유지된다.

    토큰 원문은 저장하지 않으므로 "다시 보기" 대신 재발급으로 설치 안내를 다시 받는다.
    """
    device = _get_own(db, user, device_id)
    if device.revoked_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "폐기된 기기입니다. 새 이름으로 다시 등록하세요")
    token = new_device_token()
    device.token_hash = hash_device_token(token)
    db.commit()
    return DeviceCreated(device=_to_out(device), token=token)


@router.post("/{device_id}/revoke", response_model=DeviceOut)
def revoke_device(device_id: int, db: DbSession, user: CurrentUser) -> DeviceOut:
    """토큰을 폐기한다. 이미 올라온 이번 달 사용량은 실제 사용분이므로 합계에 남는다."""
    device = _get_own(db, user, device_id)
    if device.revoked_at is None:
        device.revoked_at = datetime.now(UTC)
        db.commit()
    return _to_out(device)
