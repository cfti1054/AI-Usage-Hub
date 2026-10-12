"""Claude Code 세션 로그의 토큰 사용량을 집계해 AI Usage Hub 서버에 올리는 로컬 수집기.

사용법 (backend 폴더에서):
    uv run python -m collector.claude_code --dry-run   # 집계 결과만 출력 (서버 전송 없음)
    uv run python -m collector.claude_code             # 이번 달 누계를 서버에 업로드

환경변수:
    AIHUB_URL            예) https://ai-usage-hub-production.up.railway.app
    AIHUB_EMAIL          대시보드 로그인 이메일
    AIHUB_PASSWORD       대시보드 로그인 비밀번호
    CLAUDE_PROJECTS_DIR  (선택) 기본값 ~/.claude/projects

표준 라이브러리만 사용하므로 PC에 추가 패키지를 설치하지 않아도 된다.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SERVICE_ID = "claude-code"
METRIC_CODE = "tokens_month"
DEFAULT_TZ = "Asia/Seoul"
TIMEOUT = 30


@dataclass
class Totals:
    input: int = 0
    output: int = 0
    cache_creation: int = 0
    cache_read: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_creation + self.cache_read

    def add(self, usage: dict) -> None:
        self.input += int(usage.get("input_tokens") or 0)
        self.output += int(usage.get("output_tokens") or 0)
        self.cache_creation += int(usage.get("cache_creation_input_tokens") or 0)
        self.cache_read += int(usage.get("cache_read_input_tokens") or 0)


@dataclass
class Aggregate:
    month: Totals = field(default_factory=Totals)
    today: Totals = field(default_factory=Totals)
    by_model: dict[str, Totals] = field(default_factory=lambda: defaultdict(Totals))
    unique_messages: int = 0


def default_projects_dir() -> Path:
    override = os.environ.get("CLAUDE_PROJECTS_DIR")
    return Path(override) if override else Path.home() / ".claude" / "projects"


def iter_assistant_usage(projects_dir: Path) -> Iterator[tuple[str, str | None, str, dict]]:
    """어시스턴트 메시지의 사용량을 (message_id, timestamp, model, usage)로 낸다.

    Claude Code는 한 응답을 여러 줄로 기록하는데, 같은 message.id의 사용량 값은 모두 같다.
    그래서 message.id 기준으로 한 번만 센다. 파일이 깨졌거나 형식이 다른 줄은 건너뛴다.
    """
    seen: set[str] = set()
    for path in sorted(projects_dir.rglob("*.jsonl")):
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict) or rec.get("type") != "assistant":
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                msg_id = msg.get("id")
                if not isinstance(usage, dict) or not msg_id or msg_id in seen:
                    continue
                seen.add(msg_id)
                yield msg_id, rec.get("timestamp"), msg.get("model") or "unknown", usage


def aggregate(records: Iterator[tuple[str, str | None, str, dict]], today: date, tz: ZoneInfo) -> Aggregate:
    """오늘과 이번 달(현지 시간 기준) 사용량을 집계한다. 미래 날짜와 다른 달은 제외."""
    result = Aggregate()
    for _msg_id, ts, model, usage in records:
        result.unique_messages += 1
        if not ts:
            continue
        local_day = datetime.fromisoformat(ts).astimezone(tz).date()
        if (local_day.year, local_day.month) != (today.year, today.month) or local_day > today:
            continue
        result.month.add(usage)
        result.by_model[model].add(usage)
        if local_day == today:
            result.today.add(usage)
    return result


def build_payload(agg: Aggregate, today: date) -> dict:
    """이번 달 누계를 하나의 사용량 스냅샷으로 보낸다. 대시보드는 최신 스냅샷을 표시한다."""
    last_day = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    return {
        "service_id": SERVICE_ID,
        "source_type": "cli",
        "usage": {
            "metric_code": METRIC_CODE,
            "used_value": agg.month.total,
            "unit": "tokens",
            "period_start": today.replace(day=1).isoformat(),
            "period_end": last_day.isoformat(),
        },
    }


def _request(url: str, body: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return json.loads(res.read() or b"{}")


def login(base_url: str, email: str, password: str) -> str:
    try:
        body = _request(f"{base_url}/api/auth/login", {"email": email, "password": password})
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"로그인 실패 (HTTP {exc.code}): 이메일과 비밀번호를 확인하세요") from exc
    return body["access_token"]


def upload(base_url: str, token: str, payload: dict) -> None:
    try:
        _request(f"{base_url}/api/usage/manual", payload, token=token)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"업로드 실패 (HTTP {exc.code}): 서버 로그를 확인하세요") from exc


def print_summary(agg: Aggregate, today: date) -> None:
    def line(label: str, t: Totals) -> str:
        return (
            f"  {label:<10} 합계 {t.total:>14,}  "
            f"(입력 {t.input:,} / 출력 {t.output:,} / 캐시생성 {t.cache_creation:,} / 캐시읽기 {t.cache_read:,})"
        )

    print(f"기준일: {today.isoformat()}  고유 메시지: {agg.unique_messages:,}건")
    print(line("오늘", agg.today))
    print(line("이번 달", agg.month))
    if agg.by_model:
        print("모델별 이번 달 합계:")
        for model, t in sorted(agg.by_model.items(), key=lambda kv: -kv[1].total):
            print(f"  {model:<32} {t.total:>14,}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claude Code 토큰 사용량을 AI Usage Hub에 업로드")
    parser.add_argument("--dry-run", action="store_true", help="집계만 출력하고 서버로 보내지 않는다")
    parser.add_argument("--projects-dir", type=Path, default=None, help="세션 로그 폴더 (기본: ~/.claude/projects)")
    parser.add_argument("--tz", default=os.environ.get("AIHUB_TZ", DEFAULT_TZ), help="날짜 계산 시간대")
    args = parser.parse_args(argv)

    projects_dir = args.projects_dir or default_projects_dir()
    if not projects_dir.is_dir():
        print(f"세션 로그 폴더를 찾을 수 없습니다: {projects_dir}", file=sys.stderr)
        return 1

    tz = ZoneInfo(args.tz)
    today = datetime.now(tz).date()
    agg = aggregate(iter_assistant_usage(projects_dir), today, tz)
    print_summary(agg, today)

    if args.dry_run:
        print("\n--dry-run: 서버로 보내지 않았습니다.")
        return 0

    base_url = os.environ.get("AIHUB_URL", "").rstrip("/")
    email = os.environ.get("AIHUB_EMAIL", "")
    password = os.environ.get("AIHUB_PASSWORD", "")
    if not (base_url and email and password):
        print("AIHUB_URL, AIHUB_EMAIL, AIHUB_PASSWORD 환경변수를 설정하세요", file=sys.stderr)
        return 1

    token = login(base_url, email, password)
    upload(base_url, token, build_payload(agg, today))
    print(f"\n업로드 완료: 이번 달 {agg.month.total:,} tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
