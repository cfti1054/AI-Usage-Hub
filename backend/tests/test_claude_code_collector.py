import json
from datetime import date
from zoneinfo import ZoneInfo

from collector.claude_code import aggregate, build_payload, iter_assistant_usage

TZ = ZoneInfo("Asia/Seoul")
TODAY = date(2026, 10, 12)


def assistant(msg_id, ts, model="claude-opus-5-5", **usage):
    return {
        "type": "assistant",
        "timestamp": ts,
        "message": {
            "id": msg_id,
            "model": model,
            "usage": {
                "input_tokens": usage.get("input", 0),
                "output_tokens": usage.get("output", 0),
                "cache_creation_input_tokens": usage.get("cache_creation", 0),
                "cache_read_input_tokens": usage.get("cache_read", 0),
            },
        },
    }


def write_log(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) if isinstance(r, dict) else r for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_same_message_id_is_counted_once_across_lines_and_files(tmp_path):
    rec = assistant("msg_1", "2026-10-12T01:00:00Z", input=10, output=5)
    write_log(tmp_path / "a" / "s1.jsonl", [rec, rec, {"type": "user"}])
    write_log(tmp_path / "b" / "s2.jsonl", [rec])

    agg = aggregate(iter_assistant_usage(tmp_path), TODAY, TZ)
    assert agg.unique_messages == 1
    assert agg.month.total == 15


def test_malformed_and_unrelated_lines_are_skipped(tmp_path):
    write_log(
        tmp_path / "s.jsonl",
        ["not json", json.dumps({"type": "assistant", "message": "str"}), json.dumps(assistant("m", "2026-10-12T00:00:00Z", input=3))],
    )
    agg = aggregate(iter_assistant_usage(tmp_path), TODAY, TZ)
    assert agg.month.total == 3


def test_month_and_today_use_local_timezone(tmp_path):
    write_log(
        tmp_path / "s.jsonl",
        [
            # 2026-10-11 23:30 UTC == 2026-10-12 08:30 KST → 오늘
            assistant("a", "2026-10-11T23:30:00Z", input=100),
            # 2026-10-11 10:00 UTC == 2026-10-11 19:00 KST → 어제 (이번 달, 오늘 아님)
            assistant("b", "2026-10-11T10:00:00Z", output=50),
            # 지난달 → 제외
            assistant("c", "2026-09-30T10:00:00Z", input=999),
            # 미래 날짜 → 제외
            assistant("d", "2026-10-20T10:00:00Z", input=999),
        ],
    )
    agg = aggregate(iter_assistant_usage(tmp_path), TODAY, TZ)
    assert agg.today.total == 100
    assert agg.month.total == 150
    assert set(agg.by_model) == {"claude-opus-5-5"}


def test_cache_tokens_are_reported_separately_and_included_in_total(tmp_path):
    write_log(
        tmp_path / "s.jsonl",
        [assistant("x", "2026-10-12T00:00:00Z", input=1, output=2, cache_creation=3, cache_read=4)],
    )
    agg = aggregate(iter_assistant_usage(tmp_path), TODAY, TZ)
    assert (agg.month.input, agg.month.output, agg.month.cache_creation, agg.month.cache_read) == (1, 2, 3, 4)
    assert agg.month.total == 10


def test_payload_is_month_to_date_snapshot_for_claude_code(tmp_path):
    write_log(tmp_path / "s.jsonl", [assistant("x", "2026-10-12T00:00:00Z", input=7)])
    agg = aggregate(iter_assistant_usage(tmp_path), TODAY, TZ)
    payload = build_payload(agg, TODAY)
    assert payload == {
        "service_id": "claude-code",
        "source_type": "cli",
        "usage": {
            "metric_code": "tokens_month",
            "used_value": 7,
            "unit": "tokens",
            "period_start": "2026-10-01",
            "period_end": "2026-10-31",
        },
    }
