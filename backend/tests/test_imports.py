from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.imports.cursor_csv import CsvFormatError, parse_cursor_csv

HEADER = (
    "Date,Cloud Agent ID,Automation ID,Kind,Model,Max Mode,Input (w/ Cache Write),"
    "Input (w/o Cache Write),Cache Read,Output Tokens,Total Tokens,Cost"
)
# 사용자가 첨부한 실제 Cursor CSV 의 일부
SAMPLE = "\n".join(
    [
        HEADER,
        '"2026-08-31T07:33:36.665Z","","","Included","cursor-grok-4.6-high-fast","No","0","68682","168448","604","237734","Included"',
        '"2026-08-31T06:08:50.916Z","","","Included","cursor-grok-4.6-high-fast","No","0","65898","11264","623","77785","Included"',
        '"2026-08-30T08:31:36.065Z","","","Included","composer-2.5-fast","No","0","11519","863232","8832","883583","Included"',
        '"2026-08-04T04:04:34.950Z","","","Included","composer-2.5-fast","No","0","21009","66304","1537","88850","Included"',
    ]
)


def row(ts: datetime, model="composer-2.5-fast", inp=100, cache_write=0, cache_read=50, out=10, cost="Included") -> str:
    total = inp + cache_write + cache_read + out
    stamp = ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return f'"{stamp}","","","Included","{model}","No","{cache_write}","{inp}","{cache_read}","{out}","{total}","{cost}"'


def csv_text(*rows: str) -> str:
    return "\n".join([HEADER, *rows])


def upload(client, auth, content: str, service="cursor", filename="usage-events.csv"):
    return client.post(
        f"/api/services/{service}/usage-imports", headers=auth, json={"filename": filename, "content": content}
    )


# --- 파서 ---

def test_parse_real_cursor_sample():
    result = parse_cursor_csv("﻿" + SAMPLE)  # 엑셀 저장 시 붙는 BOM 도 허용
    assert result.rows_total == 4 and result.rows_invalid == 0
    first = result.events[0]
    assert first.occurred_at == datetime(2026, 8, 31, 7, 33, 36, 665000, tzinfo=UTC)
    assert (first.input_tokens, first.cache_creation_tokens, first.cache_read_tokens, first.output_tokens) == (68682, 0, 168448, 604)
    assert first.total_tokens == 237734 == 68682 + 168448 + 604
    assert first.kind == "Included" and first.cost_usd is None
    assert sum(e.total_tokens for e in result.events) == 237734 + 77785 + 883583 + 88850


def test_parse_numeric_cost_commas_and_reordered_columns():
    text = 'Model,Date,Cost,Output Tokens,Cache Read,Input (w/o Cache Write),Input (w/ Cache Write)\n'
    text += 'claude-4,2026-10-01T00:00:00Z,$0.0425,"1,000",0,"2,000",500\n'
    e = parse_cursor_csv(text).events[0]
    assert (e.input_tokens, e.output_tokens, e.cache_creation_tokens, e.total_tokens) == (2000, 1000, 500, 3500)
    assert e.cost_usd == Decimal("0.0425")


def test_parse_skips_bad_rows_with_reasons():
    result = parse_cursor_csv(csv_text(row(datetime(2026, 10, 1, tzinfo=UTC)), '"not-a-date","","","","m","No","0","1","0","0","1",""', ""))
    assert len(result.events) == 1 and result.rows_invalid == 1
    assert result.errors[0].startswith("3행")


def test_parse_rejects_wrong_format():
    with pytest.raises(CsvFormatError, match="없는 열"):
        parse_cursor_csv("a,b,c\n1,2,3\n")
    with pytest.raises(CsvFormatError):
        parse_cursor_csv("")


# --- API ---

def test_upload_counts_and_reupload_is_deduplicated(client, auth):
    res = upload(client, auth, SAMPLE)
    assert res.status_code == 201
    rec = res.json()["record"]
    assert (rec["rows_total"], rec["rows_added"], rec["rows_duplicate"], rec["rows_invalid"]) == (4, 4, 0, 0)
    assert rec["period_from"].startswith("2026-08-04") and rec["period_to"].startswith("2026-08-31")

    again = upload(client, auth, SAMPLE).json()["record"]
    assert (again["rows_added"], again["rows_duplicate"]) == (0, 4)


def test_overlapping_partial_ranges_only_add_new_requests(client, auth):
    now = datetime.now(UTC)
    a, b, c = now - timedelta(minutes=30), now - timedelta(minutes=20), now - timedelta(minutes=10)
    first = upload(client, auth, csv_text(row(a), row(b))).json()["record"]
    second = upload(client, auth, csv_text(row(b), row(c))).json()["record"]  # b 가 겹침
    assert (first["rows_added"], second["rows_added"], second["rows_duplicate"]) == (2, 1, 1)

    summary = client.get("/api/dashboard/summary", headers=auth).json()
    card = next(x for x in summary["services"] if x["id"] == "cursor")
    assert card["data_state"] == "ok"
    assert Decimal(card["usage"]["used_value"]) == Decimal(160 * 3)
    assert card["usage"]["metric_code"] == "tokens_month" and card["usage"]["source_type"] == "manual"
    assert [(s["kind"], s["name"]) for s in card["devices"]] == [("csv", "CSV 업로드")]


def test_service_detail_monthly_totals_and_delete(client, auth):
    upload(client, auth, SAMPLE)  # 2026-08 (오늘 기준 12개월 안이어야 집계됨)
    now = datetime.now(UTC)
    rec = upload(client, auth, csv_text(row(now - timedelta(minutes=5), inp=1000, cache_read=0, out=0))).json()["record"]

    detail = client.get("/api/services/cursor/usage", headers=auth).json()
    assert detail["csv_import_supported"] is True
    months = {m["period"]: m for m in detail["token_months"]}
    if "2026-08" in months:  # 테스트 실행 시점이 2027-08 이후면 12개월 범위를 벗어남
        aug = months["2026-08"]
        assert aug["total"] == 237734 + 77785 + 883583 + 88850 and aug["csv"] == aug["total"] and aug["devices"] == 0
        assert aug["input"] + aug["output"] + aug["cache_creation"] + aug["cache_read"] == aug["total"]

    imports = client.get("/api/services/cursor/usage-imports", headers=auth).json()
    assert [i["id"] for i in imports][0] == rec["id"]  # 최근 업로드가 먼저

    assert client.delete(f"/api/usage-imports/{rec['id']}", headers=auth).json() == {"removed_events": 1}
    card = next(x for x in client.get("/api/dashboard/summary", headers=auth).json()["services"] if x["id"] == "cursor")
    assert card["devices"] == []  # 이번 달 CSV 값이 사라짐
    assert client.delete(f"/api/usage-imports/{rec['id']}", headers=auth).status_code == 404


def test_upload_errors(client, auth):
    assert upload(client, auth, SAMPLE, service="claude-code").status_code == 400  # CSV 미지원 서비스
    assert upload(client, auth, SAMPLE, service="nope").status_code == 404
    assert upload(client, auth, "a,b\n1,2").status_code == 422
    assert upload(client, auth, HEADER + "\n").status_code == 422  # 행 없음
    assert client.get("/api/services/claude-code/usage", headers=auth).json()["csv_import_supported"] is False
