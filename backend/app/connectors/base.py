"""서비스 커넥터 공통 인터페이스.

기획서의 Provider(fetchUsage → UsageRecord[]) 인터페이스를 확정 스키마에 맞게 바꿨다.
커넥터는 정규화된 UsageSnapshot/비용 데이터만 반환하고, DB 저장·sync_jobs 기록은
app.sync 가 담당한다. 새 서비스는 이 클래스를 구현한 파일 하나를 추가하고
registry 에 등록하면 연동된다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, Literal


class ConnectorError(Exception):
    """수집 실패. 메시지는 sync_jobs.error_message 로 저장된다 (API 키는 마스킹됨)."""


@dataclass
class SnapshotData:
    metric_code: str
    used_value: Decimal | None
    limit_value: Decimal | None = None
    unit: str | None = None
    # 서비스가 해당 지표를 제공하지 않으면 'unavailable' — 0으로 채우지 않는다
    status: Literal["ok", "unavailable"] = "ok"
    period_start: date | None = None
    period_end: date | None = None
    resets_at: datetime | None = None
    raw: dict[str, Any] | None = None


@dataclass
class CostData:
    amount: Decimal
    currency: str
    cost_date: date
    granularity: Literal["day", "month"] = "day"
    cost_type: Literal["api_usage", "other"] = "api_usage"


@dataclass
class ConnectorResult:
    snapshots: list[SnapshotData] = field(default_factory=list)
    costs: list[CostData] = field(default_factory=list)


@dataclass
class ConnectorContext:
    service_id: str
    secret: str | None
    since: date
    until: date


class Connector(ABC):
    key: ClassVar[str]
    source_type: ClassVar[Literal["api", "cli"]]
    requires_secret: ClassVar[bool] = True

    @abstractmethod
    def fetch(self, ctx: ConnectorContext) -> ConnectorResult: ...

    @abstractmethod
    def test_connection(self, ctx: ConnectorContext) -> bool: ...
