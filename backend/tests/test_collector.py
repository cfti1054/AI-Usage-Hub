import json
from datetime import date
from zoneinfo import ZoneInfo

from collector.agent import apply_config, build_snapshots, collect, load_config_file
from collector.claude_code import ClaudeCodeSource
from collector.codex import CodexSource, parse_file
from collector.common import aggregate_by_month, previous_month_start

TZ = ZoneInfo("Asia/Seoul")
TODAY = date(2026, 10, 12)
MONTHS = {date(2026, 10, 1), date(2026, 9, 1)}


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in records) + "\n", encoding="utf-8")


# --- Claude Code ---

def claude(msg_id, ts, model="claude-opus-5-5", **u):
    return {
        "type": "assistant",
        "timestamp": ts,
        "message": {
            "id": msg_id,
            "model": model,
            "usage": {
                "input_tokens": u.get("input", 0),
                "output_tokens": u.get("output", 0),
                "cache_creation_input_tokens": u.get("cache_creation", 0),
                "cache_read_input_tokens": u.get("cache_read", 0),
            },
        },
    }


def test_claude_same_message_counted_once_across_lines_and_files(tmp_path):
    rec = claude("msg_1", "2026-10-12T01:00:00Z", input=10, output=5)
    write_jsonl(tmp_path / "a" / "s1.jsonl", [rec, rec, {"type": "user"}, "not json"])
    write_jsonl(tmp_path / "b" / "s2.jsonl", [rec])
    usage = aggregate_by_month(ClaudeCodeSource(tmp_path).events(), TZ, TODAY, MONTHS)
    assert usage[date(2026, 10, 1)].total.total == 15


def test_claude_local_timezone_month_and_day_buckets(tmp_path):
    write_jsonl(
        tmp_path / "s.jsonl",
        [
            claude("a", "2026-10-11T23:30:00Z", input=100),  # KST 10/12 → 오늘
            claude("b", "2026-10-11T10:00:00Z", output=50),  # KST 10/11
            claude("c", "2026-09-30T16:00:00Z", input=7),  # KST 10/01 01:00 → 이번 달
            claude("d", "2026-09-29T10:00:00Z", input=3),  # 지난달
            claude("e", "2026-08-01T10:00:00Z", input=999),  # 두 달 전 → 제외
            claude("f", "2026-10-20T10:00:00Z", input=999),  # 미래 → 제외
        ],
    )
    usage = aggregate_by_month(ClaudeCodeSource(tmp_path).events(), TZ, TODAY, MONTHS)
    october = usage[date(2026, 10, 1)]
    assert october.total.total == 157
    assert october.by_day[TODAY].total == 100
    assert october.by_day[date(2026, 10, 1)].total == 7
    assert usage[date(2026, 9, 1)].total.total == 3


def test_claude_cache_reparses_only_changed_files(tmp_path):
    path = tmp_path / "s.jsonl"
    write_jsonl(path, [claude("a", "2026-10-12T00:00:00Z", input=1)])
    source = ClaudeCodeSource(tmp_path)
    assert sum(e.tokens.total for e in source.events()) == 1
    write_jsonl(path, [claude("a", "2026-10-12T00:00:00Z", input=1), claude("b", "2026-10-12T00:01:00Z", input=2)])
    assert sum(e.tokens.total for e in source.events()) == 3


# --- Codex ---

def codex_meta(session_id, ts, forked_from=None):
    payload = {"id": session_id, "timestamp": ts}
    if forked_from:
        payload["forked_from_id"] = forked_from
    return {"timestamp": ts, "type": "session_meta", "payload": payload}


def codex_turn(ts, model="gpt-5-codex"):
    return {"timestamp": ts, "type": "turn_context", "payload": {"model": model}}


def codex_count(ts, inp, cached, out, info=True):
    usage = {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": out, "reasoning_output_tokens": 0}
    return {
        "timestamp": ts,
        "type": "event_msg",
        "payload": {"type": "token_count", "info": {"total_token_usage": usage, "last_token_usage": usage} if info else None},
    }


def test_codex_cumulative_totals_become_deltas(tmp_path):
    path = tmp_path / "sessions" / "2026" / "10" / "12" / "rollout-1.jsonl"
    write_jsonl(
        path,
        [
            codex_meta("s1", "2026-10-12T00:00:00Z"),
            codex_turn("2026-10-12T00:00:01Z"),
            codex_count("2026-10-12T00:01:00Z", inp=100, cached=40, out=10),
            codex_count("2026-10-12T00:01:01Z", inp=100, cached=40, out=10),  # 같은 누적값 반복 → 0
            codex_count("2026-10-12T00:01:02Z", 0, 0, 0, info=False),  # info 없음 → 무시
            codex_count("2026-10-12T00:02:00Z", inp=250, cached=140, out=30),
        ],
    )
    session_id, events = parse_file(path)
    assert session_id == "s1"
    assert [(e.tokens.input, e.tokens.cache_read, e.tokens.output) for e in events] == [(60, 40, 10), (50, 100, 20)]
    assert {e.model for e in events} == {"gpt-5-codex"}
    assert sum(e.tokens.total for e in events) == 280  # input_tokens 250 + output 30 (캐시는 input 안에 포함)


def test_codex_fork_skips_replayed_parent_history(tmp_path):
    path = tmp_path / "sessions" / "2026" / "10" / "12" / "rollout-2.jsonl"
    write_jsonl(
        path,
        [
            codex_meta("child", "2026-10-12T05:00:00Z", forked_from="parent"),
            codex_count("2026-10-12T01:00:00Z", inp=500, cached=0, out=50),  # 부모 시각으로 재기록된 이력
            codex_count("2026-10-12T05:10:00Z", inp=600, cached=0, out=60),  # 포크 이후 증가분만 집계
        ],
    )
    _, events = parse_file(path)
    assert [e.tokens.total for e in events] == [110]


def test_codex_archived_duplicate_session_counted_once(tmp_path):
    records = [codex_meta("same", "2026-10-12T00:00:00Z"), codex_count("2026-10-12T00:01:00Z", 10, 0, 1)]
    write_jsonl(tmp_path / "sessions" / "2026" / "10" / "12" / "rollout-a.jsonl", records)
    write_jsonl(tmp_path / "archived_sessions" / "rollout-a.jsonl", records)
    assert sum(e.tokens.total for e in CodexSource(tmp_path).events()) == 11


# --- agent payload ---

def test_collect_builds_month_and_day_rows_for_available_sources(tmp_path):
    claude_dir = tmp_path / "claude"
    write_jsonl(claude_dir / "s.jsonl", [claude("a", "2026-10-12T00:00:00Z", input=5, cache_read=5)])
    missing_codex = CodexSource(tmp_path / "no-codex")
    snapshots, summary = collect([ClaudeCodeSource(claude_dir), missing_codex], TZ, TODAY)

    assert set(summary) == {"Claude Code"}
    month_rows = [s for s in snapshots if s["metric_code"] == "tokens_month"]
    assert [(r["period_start"], r["used_value"]) for r in month_rows] == [("2026-09-01", 0), ("2026-10-01", 10)]
    october = month_rows[1]
    assert october["service_id"] == "claude-code" and october["period_end"] == "2026-10-31"
    assert october["raw"]["cache_read"] == 5 and october["raw"]["by_model"] == {"claude-opus-5-5": 10}
    day_rows = [s for s in snapshots if s["metric_code"] == "tokens_day"]
    assert day_rows == [
        {
            "service_id": "claude-code",
            "metric_code": "tokens_day",
            "used_value": 10,
            "unit": "tokens",
            "period_start": "2026-10-12",
            "period_end": "2026-10-12",
            "raw": {"input": 5, "output": 0, "cache_creation": 0, "cache_read": 5},
        }
    ]


def test_config_file_parsing_and_env_precedence(tmp_path, monkeypatch):
    path = tmp_path / "agent.env"
    path.write_text(
        "# 주석\n\nAIHUB_URL=https://example.up.railway.app\nexport AIHUB_DEVICE_TOKEN='aihub_dev_abc'\nUNKNOWN=1\n",
        encoding="utf-8",
    )
    values = load_config_file(path)
    assert values == {"AIHUB_URL": "https://example.up.railway.app", "AIHUB_DEVICE_TOKEN": "aihub_dev_abc"}
    assert load_config_file(tmp_path / "missing.env") == {}

    monkeypatch.setenv("AIHUB_URL", "https://from-env")
    monkeypatch.delenv("AIHUB_DEVICE_TOKEN", raising=False)
    apply_config(values)
    import os

    assert os.environ["AIHUB_URL"] == "https://from-env"  # 환경변수가 우선
    assert os.environ["AIHUB_DEVICE_TOKEN"] == "aihub_dev_abc"


def test_previous_month_start_handles_january():
    assert previous_month_start(date(2027, 1, 15)) == date(2026, 12, 1)
    assert build_snapshots("codex", {}) == []
