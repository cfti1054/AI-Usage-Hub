"""DB 스키마 — 기획서 5장의 7개 테이블에 검증 과정에서 보완한 내용을 반영했다.

보완 내역은 docs/initial-development.md 의 "DB 스키마 확정안" 참고.
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


class UsageSnapshot(Base):
    __tablename__ = "usage_snapshots"
    __table_args__ = (
        CheckConstraint("status IN ('ok', 'unavailable')", name="ck_usage_snapshots_status"),
        CheckConstraint("source_type IN ('api', 'cli', 'manual')", name="ck_usage_snapshots_source"),
        Index("ix_usage_snapshots_service_captured", "service_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    service_id: Mapped[str] = mapped_column(ForeignKey("ai_services.id"))
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
