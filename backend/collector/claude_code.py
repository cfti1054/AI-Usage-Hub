"""Claude Code 세션 로그 파서.

위치: ~/.claude/projects/**/*.jsonl (CLAUDE_PROJECTS_DIR 로 변경 가능)
형식: type="assistant" 인 줄의 message.usage 에 입력·출력·캐시 생성·캐시 읽기 토큰이 있다.
Claude Code 는 한 응답을 여러 줄로 기록하며 같은 message.id 의 사용량 값은 모두 같으므로,
message.id 기준으로 한 번만 센다.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

from collector.common import FileCache, Totals, UsageEvent

SERVICE_ID = "claude-code"


def default_dir() -> Path:
    override = os.environ.get("CLAUDE_PROJECTS_DIR")
    return Path(override) if override else Path.home() / ".claude" / "projects"


def parse_file(path: Path) -> list[tuple[str, UsageEvent]]:
    """파일 하나에서 (message_id, 사용량) 목록. 깨진 줄·다른 형식의 줄은 건너뛴다."""
    items: list[tuple[str, UsageEvent]] = []
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
            usage, msg_id, ts = msg.get("usage"), msg.get("id"), rec.get("timestamp")
            if not isinstance(usage, dict) or not msg_id or not ts:
                continue
            tokens = Totals(
                input=int(usage.get("input_tokens") or 0),
                output=int(usage.get("output_tokens") or 0),
                cache_creation=int(usage.get("cache_creation_input_tokens") or 0),
                cache_read=int(usage.get("cache_read_input_tokens") or 0),
            )
            items.append((msg_id, UsageEvent(timestamp=ts, model=msg.get("model") or "unknown", tokens=tokens)))
    return items


class ClaudeCodeSource:
    service_id = SERVICE_ID
    label = "Claude Code"

    def __init__(self, root: Path | None = None):
        self.root = root or default_dir()
        self._cache: FileCache[list[tuple[str, UsageEvent]]] = FileCache(parse_file)

    def available(self) -> bool:
        return self.root.is_dir()

    def events(self) -> Iterator[UsageEvent]:
        files = sorted(self.root.rglob("*.jsonl"))
        self._cache.prune(set(files))
        seen: set[str] = set()
        for path in files:
            try:
                items = self._cache.get(path)
            except OSError:  # 집계 도중 삭제·이동된 파일
                continue
            for msg_id, event in items:
                if msg_id in seen:
                    continue
                seen.add(msg_id)
                yield event
