import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CollectionMethod = Literal["api", "cli", "manual"]
Currency = Literal["KRW", "USD"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth ---
class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- services ---
class ServiceCreate(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,40}$")
    name: str
    provider: str
    collection_method: CollectionMethod = "manual"
    connector: str | None = None


class ServiceUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    collection_method: CollectionMethod | None = None
    connector: str | None = None
    enabled: bool | None = None


class ServiceOut(ORM):
    id: str
    name: str
    provider: str
    collection_method: str
    connector: str | None
    enabled: bool
    connector_available: bool = False
    has_credential: bool = False
    credential_hint: str | None = None


class CredentialIn(BaseModel):
    secret: str = Field(min_length=8)


class CredentialOut(BaseModel):
    hint: str
    updated_at: datetime | None


class ConnectionTestOut(BaseModel):
    ok: bool
    message: str


# --- subscriptions ---
class SubscriptionIn(BaseModel):
    service_id: str
    plan_name: str
    billing_cycle: Literal["monthly", "annual"] = "monthly"
    price: Decimal = Field(ge=0)
    currency: Currency
    renewal_date: date | None = None
    is_active: bool = True


class SubscriptionUpdate(BaseModel):
    plan_name: str | None = None
    billing_cycle: Literal["monthly", "annual"] | None = None
    price: Decimal | None = Field(default=None, ge=0)
    currency: Currency | None = None
    renewal_date: date | None = None
    is_active: bool | None = None


class SubscriptionOut(ORM):
    id: int
    service_id: str
    plan_name: str
    billing_cycle: str
    price: Decimal
    currency: str
    renewal_date: date | None
    is_active: bool


# --- usage / sync ---
class SnapshotOut(ORM):
    id: int
    metric_code: str
    used_value: Decimal | None
    limit_value: Decimal | None
    unit: str | None
    status: str
    period_start: date | None
    period_end: date | None
    resets_at: datetime | None
    source_type: str
    captured_at: datetime


class SyncJobOut(ORM):
    id: int
    service_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    error_message: str | None
    records_count: int
    source_type: str
    trigger: str


class ManualUsageIn(BaseModel):
    metric_code: str
    used_value: Decimal | None = None
    limit_value: Decimal | None = None
    unit: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    resets_at: datetime | None = None


class ManualCostIn(BaseModel):
    amount: Decimal = Field(ge=0)
    currency: Currency
    billing_period: str
    exchange_rate: Decimal | None = Field(default=None, gt=0)

    @field_validator("billing_period")
    @classmethod
    def check_period(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", v):
            raise ValueError("YYYY-MM 형식이어야 합니다")
        return v


class ManualEntryIn(BaseModel):
    """수동 입력. 2주차 로컬 CLI 수집기도 source_type='cli' 로 같은 엔드포인트를 사용한다."""

    service_id: str
    source_type: Literal["manual", "cli"] = "manual"
    usage: ManualUsageIn | None = None
    cost: ManualCostIn | None = None


class ManualEntryOut(BaseModel):
    snapshot_id: int | None
    cost_record_id: int | None


# --- devices / agent ---
class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("기기 이름을 입력하세요")
        return v


class DeviceOut(ORM):
    id: int
    name: str
    created_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None
    online: bool = False
    # 서비스별 이번 달 누계 (예: {"claude-code": 1234})
    month_usage: dict[str, Decimal] = {}


class DeviceCreated(BaseModel):
    device: DeviceOut
    # 이 응답에서 한 번만 내려준다. 서버에는 해시만 저장됨
    token: str


class AgentSnapshotIn(BaseModel):
    service_id: str
    metric_code: Literal["tokens_month", "tokens_day"]
    used_value: Decimal = Field(ge=0)
    unit: str = "tokens"
    period_start: date
    period_end: date
    raw: dict | None = None

    @field_validator("period_end")
    @classmethod
    def check_period(cls, v: date, info) -> date:
        start = info.data.get("period_start")
        if start and v < start:
            raise ValueError("period_end 는 period_start 이후여야 합니다")
        return v


class AgentUsageIn(BaseModel):
    snapshots: list[AgentSnapshotIn] = Field(max_length=500)


# --- settings ---
class SettingsIn(BaseModel):
    timezone: str | None = None
    currency: Currency | None = None
    alert_threshold: int | None = Field(default=None, ge=1, le=100)
    sync_interval_minutes: int | None = Field(default=None, ge=15, le=1440)


class FxIn(BaseModel):
    """환율 설정. manual 이면 fx_usd_krw 필수, auto 면 입력값은 무시하고 즉시 자동 조회한다."""

    mode: Literal["auto", "manual"]
    fx_usd_krw: Decimal | None = Field(default=None, gt=0, lt=1_000_000)
    fx_rate_date: date | None = None


class SettingsOut(ORM):
    timezone: str
    currency: str
    alert_threshold: int
    fx_mode: str
    fx_usd_krw: Decimal | None
    fx_rate_date: date | None
    fx_source: str | None
    fx_updated_at: datetime | None
    sync_interval_minutes: int


class FxOut(SettingsOut):
    # 자동 조회 실패 시 메시지 (기존 환율은 유지됨)
    fx_error: str | None = None
