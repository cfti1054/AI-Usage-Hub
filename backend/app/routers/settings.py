from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException

from app import fx, scheduler
from app.deps import CurrentUser, DbSession, get_user_settings
from app.models import UserSettings
from app.schemas import FxIn, FxOut, SettingsIn, SettingsOut

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def read_settings(db: DbSession, user: CurrentUser) -> UserSettings:
    return get_user_settings(db, user)


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsIn, db: DbSession, user: CurrentUser) -> UserSettings:
    settings = get_user_settings(db, user)
    changes = body.model_dump(exclude_unset=True)
    if "timezone" in changes:
        try:
            ZoneInfo(changes["timezone"])
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise HTTPException(422, "알 수 없는 시간대입니다") from exc
    for key, value in changes.items():
        setattr(settings, key, value)
    db.commit()
    if "sync_interval_minutes" in changes:
        scheduler.reschedule(settings.sync_interval_minutes)
    return settings


@router.put("/fx", response_model=FxOut)
def update_fx(body: FxIn, db: DbSession, user: CurrentUser) -> FxOut:
    """자동 조회 ↔ 직접 입력 전환. 자동 모드로 바꾸면 즉시 1회 조회한다."""
    settings = get_user_settings(db, user)
    if body.mode == "manual":
        if body.fx_usd_krw is None:
            raise HTTPException(422, "직접 입력 모드에는 환율 값이 필요합니다")
        settings.fx_mode = "manual"
        settings.fx_usd_krw = body.fx_usd_krw
        settings.fx_rate_date = body.fx_rate_date or datetime.now(ZoneInfo(settings.timezone)).date()
        settings.fx_source = "manual"
        settings.fx_updated_at = datetime.now(UTC)
        db.commit()
        return FxOut.model_validate(settings)

    settings.fx_mode = "auto"
    db.commit()
    return _refresh(db, settings)


@router.post("/fx/refresh", response_model=FxOut)
def refresh_fx(db: DbSession, user: CurrentUser) -> FxOut:
    settings = get_user_settings(db, user)
    if settings.fx_mode != "auto":
        raise HTTPException(409, "직접 입력 모드입니다. 자동 조회로 전환한 뒤 다시 시도하세요")
    return _refresh(db, settings)


def _refresh(db: DbSession, settings: UserSettings) -> FxOut:
    try:
        quote = fx.fetch_usd_krw()
    except fx.FxError as exc:
        # 실패해도 기존 환율은 유지하고 화면에 사유만 알린다
        out = FxOut.model_validate(settings)
        out.fx_error = str(exc)
        return out
    fx.apply_quote(settings, quote)
    db.commit()
    return FxOut.model_validate(settings)
