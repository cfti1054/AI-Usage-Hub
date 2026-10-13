from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.imports.cursor_csv import CsvFormatError
from app.imports.service import ImportNotSupported, delete_import, import_csv
from app.models import AiService, UsageImport
from app.schemas import UsageImportIn, UsageImportOut, UsageImportResult

router = APIRouter(tags=["imports"])


@router.post(
    "/api/services/{service_id}/usage-imports",
    response_model=UsageImportResult,
    status_code=status.HTTP_201_CREATED,
)
def upload_csv(service_id: str, body: UsageImportIn, db: DbSession, user: CurrentUser) -> UsageImportResult:
    """사용량 CSV 업로드. 기간이 겹치는 파일을 다시 올려도 같은 요청은 한 번만 저장된다."""
    if db.get(AiService, service_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "서비스를 찾을 수 없습니다")
    try:
        record, errors = import_csv(db, user.id, service_id, body.filename, body.content)
    except ImportNotSupported as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except CsvFormatError as exc:
        raise HTTPException(422, str(exc)) from exc
    return UsageImportResult(record=UsageImportOut.model_validate(record), errors=errors)


@router.get("/api/services/{service_id}/usage-imports", response_model=list[UsageImportOut])
def list_imports(service_id: str, db: DbSession, user: CurrentUser) -> list[UsageImport]:
    return list(
        db.scalars(
            select(UsageImport)
            .where(UsageImport.user_id == user.id, UsageImport.service_id == service_id)
            .order_by(UsageImport.uploaded_at.desc(), UsageImport.id.desc())
        )
    )


@router.delete("/api/usage-imports/{import_id}")
def remove_import(import_id: int, db: DbSession, user: CurrentUser) -> dict:
    record = db.get(UsageImport, import_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "업로드 기록을 찾을 수 없습니다")
    return {"removed_events": delete_import(db, record)}
