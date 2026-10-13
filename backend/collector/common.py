"""수집기 공통: 토큰 합계 타입, 기간별 집계, 파일 파싱 캐시.

표준 라이브러리만 사용한다 (PC 에서 추가 설치 없이 실행).
"""

from __future__ import annotations

import calendar
import os
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Generic, TypeVar
from zoneinfo import ZoneInfo


@dataclass
class Totals:
    """토큰 합계. input 은 캐시를 제외한 입력, cache_read 는 캐시에서 읽은 입력이다."""

    input: int = 0
    output: int = 0
    cache_creation: int = 0
    cache_read: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_creation + self.cache_read

    def add(self, other: Totals) -> None:
        self.input += other.input
        self.output += other.output
        self.cache_creation += other.cache_creation
        self.cache_read += other.cache_read

    def as_dict(self) -> dict[str, int]:
        return {
            "input": self.input,
            "output": self.output,
            "cache_creation": self.cache_creation,
            "cache_read": self.cache_read,
        }


@dataclass
class UsageEvent:
    """사용량 한 건. timestamp 는 ISO 8601 문자열(UTC 'Z' 포함 가능)."""

    timestamp: str
    model: str
    tokens: Totals


@dataclass
class PeriodUsage:
    total: Totals = field(default_factory=Totals)
    by_model: dict[str, Totals] = field(default_factory=lambda: defaultdict(Totals))
    by_day: dict[date, Totals] = field(default_factory=lambda: defaultdict(Totals))


def month_start(day: date) -> date:
    return day.replace(day=1)


def month_end(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def previous_month_start(day: date) -> date:
    first = month_start(day)
    return month_start(date.fromordinal(first.toordinal() - 1))


def aggregate_by_month(events: Iterable[UsageEvent], tz: ZoneInfo, today: date, months: set[date]) -> dict[date, PeriodUsage]:
    """지정한 달(월 시작일 집합)의 월 합계·모델별·일별 합계. 오늘 이후 날짜는 제외한다."""
    result: dict[date, PeriodUsage] = {m: PeriodUsage() for m in months}
    for event in events:
        try:
            day = datetime.fromisoformat(event.timestamp).astimezone(tz).date()
        except (TypeError, ValueError):
            continue
        bucket = result.get(month_start(day))
        if bucket is None or day > today:
            continue
        bucket.total.add(event.tokens)
        bucket.by_model[event.model].add(event.tokens)
        bucket.by_day[day].add(event.tokens)
    return result


T = TypeVar("T")


class FileCache(Generic[T]):
    """크기·수정 시각이 바뀐 파일만 다시 파싱한다. 에이전트가 1분마다 돌아도 부담이 적다."""

    def __init__(self, parse: Callable[[Path], T]):
        self._parse = parse
        self._entries: dict[Path, tuple[int, int, T]] = {}

    def get(self, path: Path) -> T:
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size)
        cached = self._entries.get(path)
        if cached is not None and cached[:2] == key:
            return cached[2]
        value = self._parse(path)
        self._entries[path] = (*key, value)
        return value

    def prune(self, alive: set[Path]) -> None:
        for path in list(self._entries):
            if path not in alive:
                del self._entries[path]
