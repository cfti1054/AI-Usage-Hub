"""ERD 문서 생성기. app.models 를 기준으로 docs/erd.md 의 자동 생성 구역을 다시 쓴다.

    uv run python -m app.erd           # docs/erd.md 갱신
    uv run python -m app.erd --check   # 최신이 아니면 종료 코드 1 (테스트·CI용)

자동 생성 구역(ERD:BEGIN ~ ERD:END) 밖의 설명은 손으로 관리하며 그대로 보존된다.
"""

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy import CheckConstraint, Column, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql

from app.models import Base

DOC_PATH = Path(__file__).resolve().parents[2] / "docs" / "erd.md"
BEGIN = "<!-- ERD:BEGIN — app/models.py 에서 자동 생성. 직접 수정하지 말고 `uv run python -m app.erd` 실행 -->"
END = "<!-- ERD:END -->"

_PG = postgresql.dialect()


def type_label(col: Column) -> str:
    """PostgreSQL 기준 타입 이름. Mermaid 에서 쓸 수 있도록 영숫자와 _ 만 남긴다."""
    # with_variant(…, "postgresql") 로 지정한 타입이 있으면 그것을, 없으면 기본 타입을 DDL 그대로 컴파일한다
    # (dialect_impl 은 TEXT 를 내부 구현 타입인 VARCHAR 로 바꿔 버려 실제 DDL 과 달라진다)
    pg_type = getattr(col.type, "_variant_mapping", {}).get("postgresql", col.type)
    compiled = pg_type.compile(dialect=_PG).lower()
    if compiled == "bigint" and col.primary_key and not col.foreign_keys:
        return "bigserial"
    compiled = compiled.replace("timestamp with time zone", "timestamptz")
    return re.sub(r"[^a-z0-9]+", "_", compiled).strip("_")


def _single_unique_columns(table: Table) -> set[str]:
    names = {c.name for c in table.columns if c.unique}
    for cons in table.constraints:
        if isinstance(cons, UniqueConstraint) and len(cons.columns) == 1:
            names.update(c.name for c in cons.columns)
    return names


def key_marks(col: Column, unique: set[str]) -> list[str]:
    marks = []
    if col.primary_key:
        marks.append("PK")
    if col.foreign_keys:
        marks.append("FK")
    if col.name in unique and not col.primary_key:
        marks.append("UK")
    return marks


def default_label(col: Column) -> str:
    if col.server_default is not None:
        arg = col.server_default.arg
        return f"'{arg}'" if isinstance(arg, str) else str(arg.compile(dialect=_PG))
    if col.default is not None:
        arg = col.default.arg
        if callable(arg):
            return f"{getattr(arg, '__name__', 'fn')}()"
        if isinstance(arg, bool):
            return str(arg).lower()
        return f"'{arg}'" if isinstance(arg, str) else str(arg)
    return ""


def _fk_target(col: Column) -> str:
    fk = next(iter(col.foreign_keys))
    target = f"{fk.column.table.name}.{fk.column.name}"
    return target + (f" (ON DELETE {fk.ondelete})" if fk.ondelete else "")


def render_mermaid(tables: list[Table]) -> list[str]:
    lines = ["```mermaid", "erDiagram"]
    for table in tables:
        for col in table.columns:
            for fk in col.foreign_keys:
                one_to_one = col.primary_key or col.name in _single_unique_columns(table)
                card = "||--o|" if one_to_one else "||--o{"
                lines.append(f'    {fk.column.table.name} {card} {table.name} : "{col.name}"')
    for table in tables:
        unique = _single_unique_columns(table)
        lines.append(f"    {table.name} {{")
        for col in table.columns:
            marks = key_marks(col, unique)
            parts = [type_label(col), col.name]
            if marks:
                parts.append(", ".join(marks))
            if col.nullable and not col.primary_key:
                parts.append('"NULL"')
            lines.append("        " + " ".join(parts))
        lines.append("    }")
    lines.append("```")
    return lines


def render_tables(tables: list[Table]) -> list[str]:
    lines: list[str] = []
    for table in tables:
        unique = _single_unique_columns(table)
        lines += [f"### `{table.name}`", "", "| 컬럼 | 타입 | NULL | 기본값 | 키 |", "|---|---|---|---|---|"]
        for col in table.columns:
            marks = key_marks(col, unique)
            key = ", ".join(marks)
            if col.foreign_keys:
                key += f" → `{_fk_target(col)}`"
            nullable = "Y" if col.nullable and not col.primary_key else ""
            default = default_label(col)
            lines.append(
                f"| `{col.name}` | {type_label(col)} | {nullable} | {f'`{default}`' if default else ''} | {key} |"
            )
        extras = []
        for cons in sorted(table.constraints, key=lambda c: c.name or ""):
            if isinstance(cons, CheckConstraint):
                extras.append(f"- CHECK `{cons.name}`: `{cons.sqltext}`")
            elif isinstance(cons, UniqueConstraint) and len(cons.columns) > 1:
                extras.append(f"- UNIQUE `{cons.name}`: ({', '.join(c.name for c in cons.columns)})")
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            kind = "UNIQUE INDEX" if index.unique else "INDEX"
            extras.append(f"- {kind} `{index.name}`: ({', '.join(c.name for c in index.columns)})")
        if extras:
            lines += ["", *extras]
        lines.append("")
    return lines


def render() -> str:
    tables = list(Base.metadata.sorted_tables)
    body = [
        BEGIN,
        "",
        f"테이블 {len(tables)}개. 타입은 PostgreSQL 기준입니다.",
        "",
        *render_mermaid(tables),
        "",
        *render_tables(tables),
        END,
    ]
    return "\n".join(body)


def updated_document(current: str) -> str:
    if BEGIN not in current or END not in current:
        raise SystemExit(f"{DOC_PATH} 에 자동 생성 구역 표시가 없습니다")
    head, rest = current.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    return head + render() + tail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="docs/erd.md 자동 생성 구역 갱신")
    parser.add_argument("--check", action="store_true", help="갱신하지 않고 최신 여부만 확인")
    args = parser.parse_args(argv)

    # Windows 체크아웃(CRLF)에서도 같은 결과가 나오도록 줄바꿈을 맞춘다
    current = DOC_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    new = updated_document(current)
    if args.check:
        if new != current:
            print("docs/erd.md 가 models.py 와 다릅니다. `uv run python -m app.erd` 를 실행하세요.", file=sys.stderr)
            return 1
        print("docs/erd.md 최신 상태")
        return 0
    if new != current:
        DOC_PATH.write_text(new, encoding="utf-8", newline="\n")
        print("docs/erd.md 갱신 완료")
    else:
        print("변경 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
