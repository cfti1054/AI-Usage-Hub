"""Cursor 대시보드에서 내려받은 사용량 CSV(usage-events-*.csv) 파서.

열: Date, Cloud Agent ID, Automation ID, Kind, Model, Max Mode, Input (w/ Cache Write),
    Input (w/o Cache Write), Cache Read, Output Tokens, Total Tokens, Cost

토큰 매핑 (Total = 네 항목의 합)
- Input (w/ Cache Write)  → 캐시 생성(캐시에 쓴 입력)
- Input (w/o Cache Write) → 입력
- Cache Read              → 캐시 읽기
- Output Tokens           → 출력
Cost 가 숫자("$0.12", "0.12")면 USD 로 저장하고, "Included" 같은 값이면 비용 없음으로 본다.
열 순서가 바뀌거나 대소문자·공백이 달라도 열 이름으로 찾는다. 잘못된 행은 건너뛰고 사유를 남긴다.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

COLUMNS = {
    "date": "Date",
    "model": "Model",
    "input (w/ cache write)": "Input (w/ Cache Write)",
    "input (w/o cache write)": "Input (w/o Cache Write)",
    "cache read": "Cache Read",
    "output tokens": "Output Tokens",
}
OPTIONAL = ("kind", "total tokens", "cost")
MAX_ERRORS = 20


@dataclass
class ParsedEvent:
    occurred_at: datetime  # UTC
    model: str
    kind: str | None
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    cost_usd: Decimal | None


@dataclass
class ParseResult:
    events: list[ParsedEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rows_total: int = 0
    rows_invalid: int = 0


class CsvFormatError(ValueError):
    """헤더가 맞지 않는 등 파일 전체를 읽을 수 없는 경우."""


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _int(value: str | None) -> int:
    text = (value or "").strip().replace(",", "")
    if text == "":
        return 0
    number = int(Decimal(text))
    if number < 0:
        raise ValueError("음수 토큰")
    return number


def _cost(value: str | None) -> Decimal | None:
    text = (value or "").strip().replace(",", "").removeprefix("$")
    try:
        return Decimal(text) if text else None
    except InvalidOperation:
        return None  # 'Included' 등


def _timestamp(value: str | None) -> datetime:
    dt = datetime.fromisoformat((value or "").strip())
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)


def parse_cursor_csv(text: str) -> ParseResult:
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = next(reader, None)
    if not header:
        raise CsvFormatError("빈 파일입니다")
    index = {_norm(h): i for i, h in enumerate(header)}
    missing = [label for key, label in COLUMNS.items() if key not in index]
    if missing:
        raise CsvFormatError(
            "Cursor 사용량 CSV 형식이 아닙니다. 없는 열: " + ", ".join(missing)
        )

    def cell(row: list[str], key: str) -> str | None:
        i = index.get(key)
        return row[i] if i is not None and i < len(row) else None

    result = ParseResult()
    for line_no, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        result.rows_total += 1
        try:
            input_tokens = _int(cell(row, "input (w/o cache write)"))
            cache_creation = _int(cell(row, "input (w/ cache write)"))
            cache_read = _int(cell(row, "cache read"))
            output = _int(cell(row, "output tokens"))
            total_cell = cell(row, "total tokens")
            total = _int(total_cell) if total_cell not in (None, "") else input_tokens + cache_creation + cache_read + output
            model = (cell(row, "model") or "").strip() or "unknown"
            result.events.append(
                ParsedEvent(
                    occurred_at=_timestamp(cell(row, "date")),
                    model=model,
                    kind=(cell(row, "kind") or "").strip() or None,
                    input_tokens=input_tokens,
                    output_tokens=output,
                    cache_creation_tokens=cache_creation,
                    cache_read_tokens=cache_read,
                    total_tokens=total,
                    cost_usd=_cost(cell(row, "cost")),
                )
            )
        except (ValueError, InvalidOperation) as exc:
            result.rows_invalid += 1
            if len(result.errors) < MAX_ERRORS:
                result.errors.append(f"{line_no}행: {exc}")
    return result
