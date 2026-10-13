from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.connectors import get_connector
from app.connectors.base import ConnectorContext
from app.credentials import delete_secret, get_secret, set_secret
from app import reports
from app.deps import CurrentUser, DbSession, get_user_settings
from app.imports import PARSERS
from app.models import AiService, CostRecord, ServiceCredential, SyncJob, UsageSnapshot
from app.schemas import (
    ConnectionTestOut,
    CredentialIn,
    CredentialOut,
    ServiceCreate,
    ServiceOut,
    ServiceUpdate,
    SnapshotOut,
    SyncJobOut,
)
from app.sync import SyncNotSupported, run_sync

router = APIRouter(prefix="/api/services", tags=["services"])


def _get_service(db: DbSession, service_id: str) -> AiService:
    service = db.get(AiService, service_id)
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "서비스를 찾을 수 없습니다")
    return service


def _to_out(db: DbSession, service: AiService) -> ServiceOut:
    cred = db.get(ServiceCredential, service.id)
    out = ServiceOut.model_validate(service)
    out.connector_available = get_connector(service.connector) is not None
    out.has_credential = cred is not None
    out.credential_hint = f"****{cred.hint}" if cred else None
    return out


@router.get("", response_model=list[ServiceOut])
def list_services(db: DbSession, _: CurrentUser) -> list[ServiceOut]:
    services = db.scalars(select(AiService).order_by(AiService.created_at, AiService.id)).all()
    return [_to_out(db, s) for s in services]


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(body: ServiceCreate, db: DbSession, _: CurrentUser) -> ServiceOut:
    if db.get(AiService, body.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 존재하는 서비스 ID입니다")
    service = AiService(**body.model_dump(), enabled=True)
    db.add(service)
    db.commit()
    return _to_out(db, service)


@router.patch("/{service_id}", response_model=ServiceOut)
def update_service(service_id: str, body: ServiceUpdate, db: DbSession, _: CurrentUser) -> ServiceOut:
    service = _get_service(db, service_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(service, key, value)
    db.commit()
    return _to_out(db, service)


@router.get("/{service_id}/usage")
def service_usage(
    service_id: str, db: DbSession, user: CurrentUser, days: int = Query(30, ge=1, le=366)
) -> dict:
    service = _get_service(db, service_id)
    since = datetime.now(UTC) - timedelta(days=days)
    history = db.scalars(
        select(UsageSnapshot)
        .where(
            UsageSnapshot.user_id == user.id,
            UsageSnapshot.service_id == service_id,
            UsageSnapshot.captured_at >= since,
            # 기기 에이전트 값은 아래 "devices" 에서 기기별로 따로 보여준다
            UsageSnapshot.device_id.is_(None),
        )
        .order_by(UsageSnapshot.captured_at)
    ).all()
    latest: dict[str, UsageSnapshot] = {}
    for snap in history:
        latest[snap.metric_code] = snap
    jobs = db.scalars(
        select(SyncJob).where(SyncJob.service_id == service_id).order_by(SyncJob.started_at.desc()).limit(20)
    ).all()
    costs = db.scalars(
        select(CostRecord)
        .where(
            CostRecord.user_id == user.id,
            CostRecord.service_id == service_id,
            CostRecord.cost_date >= date.today() - timedelta(days=days),
        )
        .order_by(CostRecord.cost_date)
    ).all()
    settings = get_user_settings(db, user)
    devices = reports.device_month_usage(db, user.id, settings).get(service_id, [])
    return {
        "service": _to_out(db, service),
        "csv_import_supported": service_id in PARSERS,
        # 최근 12개월 토큰 합계 (기기 에이전트 + CSV 업로드)
        "token_months": reports.token_months(db, user.id, settings, service_id),
        "devices": [
            {k: d[k] for k in ("device_id", "name", "used_value", "captured_at", "online", "revoked")}
            | {"breakdown": d["snapshot"].raw}
            for d in devices
        ],
        "latest": [SnapshotOut.model_validate(s) for s in latest.values()],
        "history": [SnapshotOut.model_validate(s) for s in history],
        "recent_jobs": [SyncJobOut.model_validate(j) for j in jobs],
        "costs": [
            {
                "cost_date": c.cost_date,
                "granularity": c.granularity,
                "amount": c.amount,
                "currency": c.currency,
                "source_type": c.source_type,
            }
            for c in costs
        ],
    }


@router.post("/{service_id}/sync", response_model=SyncJobOut)
def sync_service(service_id: str, db: DbSession, user: CurrentUser) -> SyncJob:
    service = _get_service(db, service_id)
    try:
        return run_sync(db, service, user.id, trigger="manual")
    except SyncNotSupported as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.put("/{service_id}/credential", response_model=CredentialOut)
def put_credential(service_id: str, body: CredentialIn, db: DbSession, _: CurrentUser) -> CredentialOut:
    _get_service(db, service_id)
    cred = set_secret(db, service_id, body.secret)
    return CredentialOut(hint=f"****{cred.hint}", updated_at=cred.updated_at)


@router.delete("/{service_id}/credential", status_code=status.HTTP_204_NO_CONTENT)
def remove_credential(service_id: str, db: DbSession, _: CurrentUser) -> None:
    _get_service(db, service_id)
    delete_secret(db, service_id)


@router.post("/{service_id}/test", response_model=ConnectionTestOut)
def test_connection(service_id: str, db: DbSession, _: CurrentUser) -> ConnectionTestOut:
    service = _get_service(db, service_id)
    connector = get_connector(service.connector)
    if connector is None:
        return ConnectionTestOut(ok=False, message="자동 수집 커넥터가 없는 서비스입니다")
    secret = get_secret(db, service_id)
    if connector.requires_secret and not secret:
        return ConnectionTestOut(ok=False, message="API 키가 설정되지 않았습니다")
    today = date.today()
    ctx = ConnectorContext(service_id=service_id, secret=secret, since=today, until=today)
    try:
        ok = connector.test_connection(ctx)
    except Exception:  # 상세 오류에는 키가 섞일 수 있어 응답하지 않는다
        ok = False
    return ConnectionTestOut(ok=ok, message="연결 성공" if ok else "연결 실패 — API 키와 권한을 확인하세요")
