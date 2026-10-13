import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.imports import PARSERS
from app.imports.cursor_csv import CsvFormatError
from app.models import UsageEvent, UsageImport


class ImportNotSupported(Exception):
    pass


def as_utc(dt: datetime) -> datetime:
    """SQLite 는 시간대 없이 돌려주므로 UTC 로 맞춰 비교한다."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def import_csv(db: Session, user_id: uuid.UUID, service_id: str, filename: str, text: str) -> tuple[UsageImport, list[str]]:
    """CSV 를 읽어 새 요청만 저장한다. 이미 저장된 요청(겹치는 기간 재업로드)은 중복으로 센다."""
    parser = PARSERS.get(service_id)
    if parser is None:
        raise ImportNotSupported(f"{service_id}: CSV 업로드를 지원하지 않는 서비스입니다")
    result = parser(text)
    if not result.events:
        detail = f" ({'; '.join(result.errors[:3])})" if result.errors else ""
        raise CsvFormatError(f"저장할 수 있는 행이 없습니다{detail}")

    times = [e.occurred_at for e in result.events]
    lo, hi = min(times), max(times)
    existing = {
        (as_utc(t), m, n)
        for t, m, n in db.execute(
            select(UsageEvent.occurred_at, UsageEvent.model, UsageEvent.total_tokens).where(
                UsageEvent.user_id == user_id,
                UsageEvent.service_id == service_id,
                UsageEvent.occurred_at >= lo,
                UsageEvent.occurred_at <= hi,
            )
        )
    }

    record = UsageImport(
        user_id=user_id,
        service_id=service_id,
        filename=filename[:200] or "upload.csv",
        rows_total=result.rows_total,
        rows_invalid=result.rows_invalid,
        period_from=lo,
        period_to=hi,
    )
    db.add(record)
    db.flush()

    added = duplicate = 0
    for e in result.events:
        key = (e.occurred_at, e.model, e.total_tokens)
        if key in existing:
            duplicate += 1
            continue
        existing.add(key)
        db.add(
            UsageEvent(
                user_id=user_id,
                service_id=service_id,
                import_id=record.id,
                occurred_at=e.occurred_at,
                model=e.model,
                kind=e.kind,
                input_tokens=e.input_tokens,
                output_tokens=e.output_tokens,
                cache_creation_tokens=e.cache_creation_tokens,
                cache_read_tokens=e.cache_read_tokens,
                total_tokens=e.total_tokens,
                cost_usd=e.cost_usd,
            )
        )
        added += 1
    record.rows_added = added
    record.rows_duplicate = duplicate
    db.commit()
    return record, result.errors


def delete_import(db: Session, record: UsageImport) -> int:
    """업로드와, 그 업로드로 새로 추가된 요청을 지운다. 지운 요청 수를 돌려준다."""
    removed = db.execute(delete(UsageEvent).where(UsageEvent.import_id == record.id)).rowcount
    db.delete(record)
    db.commit()
    return removed
