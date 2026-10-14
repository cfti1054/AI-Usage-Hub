"""DB 스키마.

ERD와 테이블 명세는 docs/erd.md 에 있다. 이 파일을 바꾸면 마이그레이션을 추가하고
`uv run python -m app.erd` 로 ERD 문서를 다시 생성한다 (테스트가 최신 여부를 검사함).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JsonType = JSON().with_variant(JSONB(), "postgresql")
# PostgreSQL에서는 bigserial, 테스트용 SQLite에서는 INTEGER(자동 증가)
BigId = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiService(Base):
    __tablename__ = "ai_services"
    __table_args__ = (
        CheckConstraint("collection_method IN ('api', 'cli', 'manual')", name="ck_ai_services_method"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # 'claude-code' | 'codex' | ...
    name: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)  # 'Anthropic' | 'OpenAI' | ...
    # 1차 수집 방식 — 화면의 API/CLI/수동 뱃지
    collection_method: Mapped[str] = mapped_column(Text, default="manual")
    # app.connectors 레지스트리 키. 없으면 자동 수집 대상이 아니다
    connector: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServiceCredential(Base):
    """서비스별 API 키. Fernet으로 암호화해 저장하고 평문은 절대 응답하지 않는다."""

    __tablename__ = "service_credentials"

    service_id: Mapped[str] = mapped_column(
        ForeignKey("ai_services.id", ondelete="CASCADE"), primary_key=True
    )
    encrypted_secret: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(String(8))  # 마스킹 표시용 끝 4자리
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("billing_cycle IN ('monthly', 'annual')", name="ck_subscriptions_cycle"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    service_id: Mapped[str] = mapped_column(ForeignKey("ai_services.id"))
    plan_name: Mapped[str] = mapped_column(Text)
    billing_cycle: Mapped[str] = mapped_column(Text, default="monthly")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3))  # 'KRW' | 'USD'
    renewal_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Device(Base):
    """사용량 에이전트를 실행하는 기기(PC). 토큰은 SHA-256 해시만 저장한다."""

    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_devices_user_name"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 마지막 업로드·신호
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 폐기 시각 (이후 업로드 거부)


class WidgetToken(Base):
    """휴대폰 위젯용 조회 전용 토큰. 요약 조회만 가능하고, 해시만 저장한다."""

    __tablename__ = "widget_tokens"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_widget_tokens_user_name"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(Text)  # 예: '내 아이폰'
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageSnapshot(Base):
    __tablename__ = "usage_snapshots"
    __table_args__ = (
        CheckConstraint("status IN ('ok', 'unavailable')", name="ck_usage_snapshots_status"),
        CheckConstraint("source_type IN ('api', 'cli', 'manual')", name="ck_usage_snapshots_source"),
        Index("ix_usage_snapshots_service_captured", "service_id", "captured_at"),
        # 기기 에이전트 값은 (기기, 서비스, 지표, 기간 시작) 단위로 덮어쓴다. device_id 가 NULL 인
        # 수동 입력 행은 NULL 끼리 서로 다른 값으로 취급되어 이 제약에 걸리지 않는다
        UniqueConstraint(
            "device_id", "service_id", "metric_code", "period_start", name="uq_usage_snapshots_device_bucket"
        ),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    service_id: Mapped[str] = mapped_column(ForeignKey("ai_services.id"))
    # 기기 에이전트가 올린 값이면 해당 기기. 수동 입력·API 커넥터 값은 NULL
    device_id: Mapped[int | None] = mapped_column(BigId, ForeignKey("devices.id"))
    metric_code: Mapped[str] = mapped_column(Text)  # 'tokens' | 'requests' | 'credits' | 'session' | ...
    # 수집 불가 시 0이 아니라 NULL + status='unavailable'로 저장한다
    used_value: Mapped[Decimal | None] = mapped_column(Numeric)
    limit_value: Mapped[Decimal | None] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="ok")
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    resets_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 다음 한도 초기화 시각
    source_type: Mapped[str] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict[str, Any] | None] = mapped_column(JsonType)


class UsageImport(Base):
    """CSV 업로드 1건의 이력. 삭제하면 이 업로드로 새로 추가된 이벤트만 함께 지운다."""

    __tablename__ = "usage_imports"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    service_id: Mapped[str] = mapped_column(ForeignKey("ai_services.id"))
    filename: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_added: Mapped[int] = mapped_column(Integer, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, default=0)  # 이미 올린 행과 같은 요청
    rows_invalid: Mapped[int] = mapped_column(Integer, default=0)
    period_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 파일의 가장 이른 시각
    period_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 파일의 가장 늦은 시각


class UsageEvent(Base):
    """요청 1건의 토큰 사용량 (CSV 업로드 등). 시각은 UTC 로 저장한다.

    같은 요청이 여러 파일에 겹쳐 들어와도 (서비스, 시각, 모델, 총 토큰) 이 같으면 한 번만 저장한다.
    """

    __tablename__ = "usage_events"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "service_id", "occurred_at", "model", "total_tokens", name="uq_usage_events_identity"
        ),
        Index("ix_usage_events_service_time", "service_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    service_id: Mapped[str] = mapped_column(ForeignKey("ai_services.id"))
    import_id: Mapped[int] = mapped_column(BigId, ForeignKey("usage_imports.id", ondelete="CASCADE"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    model: Mapped[str] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(Text)  # Cursor: 'Included' 등 과금 구분
    input_tokens: Mapped[int] = mapped_column(BigInteger)  # 캐시 미사용 입력
    output_tokens: Mapped[int] = mapped_column(BigInteger)
    cache_creation_tokens: Mapped[int] = mapped_column(BigInteger)  # 캐시에 쓴 입력
    cache_read_tokens: Mapped[int] = mapped_column(BigInteger)
    total_tokens: Mapped[int] = mapped_column(BigInteger)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))  # 숫자 비용이 있을 때만


class CostRecord(Base):
    """API 종량제 비용. 구독료는 subscriptions에서 계산하며 여기에 중복 저장하지 않는다."""

    __tablename__ = "cost_records"
    __table_args__ = (
        CheckConstraint("cost_type IN ('api_usage', 'other')", name="ck_cost_records_type"),
        CheckConstraint("granularity IN ('day', 'month')", name="ck_cost_records_granularity"),
        UniqueConstraint(
            "user_id", "service_id", "cost_type", "source_type", "granularity", "cost_date",
            name="uq_cost_records_bucket",
        ),
        Index("ix_cost_records_period", "billing_period"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    service_id: Mapped[str] = mapped_column(ForeignKey("ai_services.id"))
    cost_type: Mapped[str] = mapped_column(Text, default="api_usage")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    currency: Mapped[str] = mapped_column(String(3))  # 원 통화 그대로 저장
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))  # 원화 환산 시 적용 환율
    # 'day' = API 일별 버킷, 'month' = 수동 입력 월 금액 (cost_date는 해당 월 1일)
    granularity: Mapped[str] = mapped_column(Text, default="day")
    cost_date: Mapped[date] = mapped_column(Date)
    billing_period: Mapped[str] = mapped_column(String(7))  # 'YYYY-MM'
    source_type: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'failed', 'partial')", name="ck_sync_jobs_status"
        ),
        Index("ix_sync_jobs_service_started", "service_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("ai_services.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    records_count: Mapped[int] = mapped_column(Integer, default=0)
    source_type: Mapped[str] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(Text, default="manual")  # 'schedule' | 'manual'


class UserSettings(Base):
    __tablename__ = "user_settings"
    __table_args__ = (CheckConstraint("fx_mode IN ('auto', 'manual')", name="ck_user_settings_fx_mode"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    timezone: Mapped[str] = mapped_column(Text, default="Asia/Seoul")
    currency: Mapped[str] = mapped_column(String(3), default="KRW")
    alert_threshold: Mapped[int] = mapped_column(Integer, default=80)  # 한도 사용률 알림 기준(%)
    # 적용 환율. 'auto' 면 app.fx 가 주기적으로 갱신하고, 'manual' 이면 사용자가 입력한 값을 유지한다
    fx_mode: Mapped[str] = mapped_column(Text, default="auto", server_default="auto")
    fx_usd_krw: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    fx_rate_date: Mapped[date | None] = mapped_column(Date)  # 환율 기준일 (화면에 함께 표시)
    fx_source: Mapped[str | None] = mapped_column(Text)  # 'koreaexim' | 'frankfurter' | 'manual'
    fx_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
