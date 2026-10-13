"""AI Usage Hub PC 에이전트 — Claude Code·Codex 토큰 사용량을 계속 서버에 올린다.

사용법 (backend 폴더에서):
    uv run python -m collector.agent --dry-run      # 집계만 출력 (서버 전송 없음)
    uv run python -m collector.agent --once         # 한 번만 업로드
    uv run python -m collector.agent                # 상주 실행 (기본 60초 주기)
    uvw run python -m collector.agent               # 창 없이 상주 실행 (작업 스케줄러용)

설정 (환경변수 또는 ~/.aihub/agent.env 의 KEY=VALUE 줄 — 환경변수가 우선):
    AIHUB_URL            서버 주소 (예: https://ai-usage-hub-production.up.railway.app)
    AIHUB_DEVICE_TOKEN   설정 → 기기 관리에서 발급한 기기 토큰
    AIHUB_TZ             날짜 계산 시간대 (기본 Asia/Seoul)
    CLAUDE_PROJECTS_DIR  Claude Code 로그 폴더 (기본 ~/.claude/projects)
    CODEX_HOME           Codex 홈 폴더 (기본 ~/.codex)

동작: 매 주기마다 로그를 집계해 값이 바뀌었으면 업로드하고, 바뀌지 않았으면 5분마다
"살아 있음" 신호만 보낸다. 이번 달과 지난달의 월 누계·일별 합계를 함께 보내므로 PC 가 꺼져
있던 사이 놓친 값도 다음 실행 때 맞춰진다. 로그는 ~/.aihub/agent.log 에 남긴다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

from collector.claude_code import ClaudeCodeSource
from collector.codex import CodexSource
from collector.common import PeriodUsage, aggregate_by_month, month_end, month_start, previous_month_start

DEFAULT_TZ = "Asia/Seoul"
HEARTBEAT_SECONDS = 300
TIMEOUT = 30
LOG_PATH = Path.home() / ".aihub" / "agent.log"
# macOS launchd 는 셸 환경변수를 넘겨주지 않으므로 설정 파일도 읽는다
CONFIG_PATH = Path.home() / ".aihub" / "agent.env"
CONFIG_KEYS = ("AIHUB_URL", "AIHUB_DEVICE_TOKEN", "AIHUB_TZ", "CLAUDE_PROJECTS_DIR", "CODEX_HOME")


def load_config_file(path: Path = CONFIG_PATH) -> dict[str, str]:
    """KEY=VALUE 형식. 빈 줄·# 주석은 무시하고 값의 앞뒤 따옴표는 벗긴다."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        if key in CONFIG_KEYS:
            values[key] = value.strip().strip("'\"")
    return values


def apply_config(values: dict[str, str]) -> None:
    for key, value in values.items():
        if value and not os.environ.get(key):
            os.environ[key] = value

log = logging.getLogger("aihub.agent")


class AuthError(Exception):
    pass


def build_snapshots(service_id: str, months: dict[date, PeriodUsage]) -> list[dict]:
    """월 누계(tokens_month)와 일별 합계(tokens_day) 행. raw 에 토큰 종류·모델별 내역을 담는다."""
    rows: list[dict] = []
    for start, usage in sorted(months.items()):
        rows.append(
            {
                "service_id": service_id,
                "metric_code": "tokens_month",
                "used_value": usage.total.total,
                "unit": "tokens",
                "period_start": start.isoformat(),
                "period_end": month_end(start).isoformat(),
                "raw": {
                    **usage.total.as_dict(),
                    "by_model": {m: t.total for m, t in sorted(usage.by_model.items()) if t.total},
                },
            }
        )
        for day, totals in sorted(usage.by_day.items()):
            rows.append(
                {
                    "service_id": service_id,
                    "metric_code": "tokens_day",
                    "used_value": totals.total,
                    "unit": "tokens",
                    "period_start": day.isoformat(),
                    "period_end": day.isoformat(),
                    "raw": totals.as_dict(),
                }
            )
    return rows


def collect(sources: list, tz: ZoneInfo, today: date) -> tuple[list[dict], dict[str, dict[date, PeriodUsage]]]:
    months = {month_start(today), previous_month_start(today)}
    snapshots: list[dict] = []
    summary: dict[str, dict[date, PeriodUsage]] = {}
    for source in sources:
        if not source.available():
            continue
        by_month = aggregate_by_month(source.events(), tz, today, months)
        summary[source.label] = by_month
        snapshots += build_snapshots(source.service_id, by_month)
    return snapshots, summary


def _post(base_url: str, path: str, token: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json", "X-Device-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise AuthError("기기 토큰이 잘못되었거나 폐기되었습니다. 설정 → 기기 관리에서 다시 발급하세요") from exc
        raise


def print_summary(summary: dict[str, dict[date, PeriodUsage]], today: date) -> None:
    if not summary:
        print("수집할 로그가 없습니다 (Claude Code·Codex 로그 폴더를 찾지 못함)")
        return
    this_month = month_start(today)
    for label, by_month in summary.items():
        usage = by_month.get(this_month, PeriodUsage())
        today_total = usage.by_day.get(today)
        t = usage.total
        print(f"[{label}] 이번 달 {t.total:,} (입력 {t.input:,} / 출력 {t.output:,} / 캐시생성 {t.cache_creation:,} / 캐시읽기 {t.cache_read:,})")
        print(f"  오늘 {today_total.total if today_total else 0:,}")
        for model, mt in sorted(usage.by_model.items(), key=lambda kv: -kv[1].total):
            if mt.total:
                print(f"  {model:<32} {mt.total:>14,}")


def _setup_logging(to_file: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()] if sys.stderr else []
    if to_file:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)


def run(base_url: str, token: str, tz: ZoneInfo, interval: int, once: bool) -> int:
    sources = [ClaudeCodeSource(), CodexSource()]
    last_hash: str | None = None
    last_contact = 0.0
    while True:
        try:
            today = datetime.now(tz).date()
            snapshots, _ = collect(sources, tz, today)
            digest = hashlib.sha256(json.dumps(snapshots, sort_keys=True).encode()).hexdigest()
            if digest != last_hash:
                if snapshots:
                    result = _post(base_url, "/api/agent/usage", token, {"snapshots": snapshots})
                    log.info("업로드 %s행", result.get("saved"))
                else:
                    _post(base_url, "/api/agent/heartbeat", token)
                last_hash, last_contact = digest, time.monotonic()
            elif time.monotonic() - last_contact >= HEARTBEAT_SECONDS:
                _post(base_url, "/api/agent/heartbeat", token)
                last_contact = time.monotonic()
        except AuthError as exc:
            log.error("%s", exc)
            return 2
        except Exception as exc:  # 네트워크 오류 등은 다음 주기에 다시 시도
            log.warning("업로드 실패, 다음 주기에 재시도: %s", exc)
            if once:
                return 1
        if once:
            return 0
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claude Code·Codex 토큰 사용량을 AI Usage Hub 에 계속 업로드")
    parser.add_argument("--dry-run", action="store_true", help="집계만 출력하고 서버로 보내지 않는다")
    parser.add_argument("--once", action="store_true", help="한 번만 업로드하고 종료")
    parser.add_argument("--interval", type=int, default=60, help="확인 주기(초), 기본 60")
    parser.add_argument("--tz", default=None, help="날짜 계산 시간대 (기본 AIHUB_TZ 또는 Asia/Seoul)")
    args = parser.parse_args(argv)
    apply_config(load_config_file())
    args.tz = args.tz or os.environ.get("AIHUB_TZ") or DEFAULT_TZ

    tz = ZoneInfo(args.tz)
    if args.dry_run:
        today = datetime.now(tz).date()
        _, summary = collect([ClaudeCodeSource(), CodexSource()], tz, today)
        print_summary(summary, today)
        print("\n--dry-run: 서버로 보내지 않았습니다.")
        return 0

    base_url = os.environ.get("AIHUB_URL", "").rstrip("/")
    token = os.environ.get("AIHUB_DEVICE_TOKEN", "")
    if not (base_url and token):
        print(f"AIHUB_URL, AIHUB_DEVICE_TOKEN 을 환경변수 또는 {CONFIG_PATH} 에 설정하세요", file=sys.stderr)
        return 1
    _setup_logging(to_file=not args.once)
    log.info("에이전트 시작: %s, 주기 %d초", base_url, args.interval)
    return run(base_url, token, tz, max(args.interval, 15), args.once)


if __name__ == "__main__":
    raise SystemExit(main())
