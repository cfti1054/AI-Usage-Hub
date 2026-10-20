"""Codex CLI 세션(rollout) 로그 파서.

위치: $CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl, $CODEX_HOME/archived_sessions/rollout-*.jsonl
      (CODEX_HOME 기본값 ~/.codex)
형식 (openai/codex 의 codex-rs/protocol 기준):
  {"timestamp": "...", "type": "session_meta", "payload": {"id": "...", "timestamp": "...", "forked_from_id": ...}}
  {"timestamp": "...", "type": "turn_context", "payload": {"model": "...", ...}}
  {"timestamp": "...", "type": "event_msg",
   "payload": {"type": "token_count", "info": {"total_token_usage": {...}, "last_token_usage": {...}}}}

집계 규칙
- total_token_usage 는 세션 누적값이므로 직전 이벤트와의 차이를 그 시각의 사용량으로 본다.
  같은 누적값이 반복 기록되면 차이가 0이라 중복이 자연히 걸러진다.
- cached_input_tokens 는 input_tokens 에 포함된 값이라 빼서 캐시 읽기로 따로 센다.
- 포크된 세션(forked_from_id)은 부모 대화를 부모 시각 그대로 다시 기록하므로, 세션 시작 이전
  시각의 이벤트는 기준값으로만 쓰고 집계하지 않는다.
- info 가 null 인 이벤트(한도 알림 등)와 형식이 다른 줄은 건너뛴다.

로그 형식은 공식 문서가 없는 내부 형식이라 Codex 버전에 따라 바뀔 수 있다.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from collector.common import FileCache, Totals, UsageEvent, parse_iso

SERVICE_ID = "codex"
_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens")


def default_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    return Path(override) if override else Path.home() / ".codex"


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return parse_iso(value)
    except ValueError:
        return None


def _counters(usage: object) -> tuple[int, ...] | None:
    if not isinstance(usage, dict):
        return None
    try:
        return tuple(int(usage.get(f) or 0) for f in _FIELDS)
    except (TypeError, ValueError):
        return None


def _to_totals(delta: tuple[int, ...]) -> Totals:
    inp, cached, cache_write, out = delta
    return Totals(input=max(inp - cached, 0), output=out, cache_creation=cache_write, cache_read=cached)


def parse_file(path: Path) -> tuple[str, list[UsageEvent]]:
    """(세션 ID, 사용량 이벤트 목록). session_meta 가 없으면 파일 경로를 세션 ID 로 쓴다."""
    session_id = str(path)
    session_start: datetime | None = None
    forked = False
    model = "unknown"
    prev: tuple[int, ...] | None = None
    events: list[UsageEvent] = []

    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            kind, payload = rec.get("type"), rec.get("payload")
            if not isinstance(payload, dict):
                continue

            if kind == "session_meta":
                session_id = str(payload.get("id") or session_id)
                session_start = _parse_ts(payload.get("timestamp")) or _parse_ts(rec.get("timestamp"))
                forked = bool(payload.get("forked_from_id"))
                continue
            if kind == "turn_context":
                model = str(payload.get("model") or model)
                continue
            if kind != "event_msg" or payload.get("type") != "token_count":
                continue

            info = payload.get("info")
            current = _counters(info.get("total_token_usage")) if isinstance(info, dict) else None
            ts = rec.get("timestamp")
            if current is None or not isinstance(ts, str):
                continue

            if prev is None or any(c < p for c, p in zip(current, prev, strict=True)):
                delta = current  # 첫 이벤트 또는 누적값 초기화
            else:
                delta = tuple(c - p for c, p in zip(current, prev, strict=True))
            prev = current

            event_time = _parse_ts(ts)
            if forked and session_start and event_time and event_time < session_start:
                continue  # 부모 세션에서 이미 센 사용량
            if any(delta):
                events.append(UsageEvent(timestamp=ts, model=model, tokens=_to_totals(delta)))
    return session_id, events


class CodexSource:
    service_id = SERVICE_ID
    label = "Codex"

    def __init__(self, home: Path | None = None):
        self.home = home or default_home()
        self._cache: FileCache[tuple[str, list[UsageEvent]]] = FileCache(parse_file)

    def _files(self) -> list[Path]:
        files = list((self.home / "sessions").rglob("rollout-*.jsonl"))
        files += list((self.home / "archived_sessions").glob("rollout-*.jsonl"))
        return sorted(files)

    def available(self) -> bool:
        return (self.home / "sessions").is_dir() or (self.home / "archived_sessions").is_dir()

    def events(self) -> Iterator[UsageEvent]:
        files = self._files()
        self._cache.prune(set(files))
        seen: set[str] = set()
        for path in files:
            try:
                session_id, events = self._cache.get(path)
            except OSError:
                continue
            if session_id in seen:  # 보관(archived)과 활성 폴더에 같은 세션이 있는 경우
                continue
            seen.add(session_id)
            yield from events
