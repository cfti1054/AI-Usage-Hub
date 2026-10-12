"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-12 14:19:24.834301
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('ai_services',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('provider', sa.Text(), nullable=False),
    sa.Column('collection_method', sa.Text(), nullable=False),
    sa.Column('connector', sa.Text(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("collection_method IN ('api', 'cli', 'manual')", name='ck_ai_services_method'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('cost_records',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('service_id', sa.Text(), nullable=False),
    sa.Column('cost_type', sa.Text(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=4), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=10, scale=4), nullable=True),
    sa.Column('granularity', sa.Text(), nullable=False),
    sa.Column('cost_date', sa.Date(), nullable=False),
    sa.Column('billing_period', sa.String(length=7), nullable=False),
    sa.Column('source_type', sa.Text(), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("cost_type IN ('api_usage', 'other')", name='ck_cost_records_type'),
    sa.CheckConstraint("granularity IN ('day', 'month')", name='ck_cost_records_granularity'),
    sa.ForeignKeyConstraint(['service_id'], ['ai_services.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'service_id', 'cost_type', 'source_type', 'granularity', 'cost_date', name='uq_cost_records_bucket')
    )
    op.create_index('ix_cost_records_period', 'cost_records', ['billing_period'], unique=False)
    op.create_table('service_credentials',
    sa.Column('service_id', sa.Text(), nullable=False),
    sa.Column('encrypted_secret', sa.Text(), nullable=False),
    sa.Column('hint', sa.String(length=8), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['service_id'], ['ai_services.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('service_id')
    )
    op.create_table('subscriptions',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('service_id', sa.Text(), nullable=False),
    sa.Column('plan_name', sa.Text(), nullable=False),
    sa.Column('billing_cycle', sa.Text(), nullable=False),
    sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('renewal_date', sa.Date(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("billing_cycle IN ('monthly', 'annual')", name='ck_subscriptions_cycle'),
    sa.ForeignKeyConstraint(['service_id'], ['ai_services.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sync_jobs',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('service_id', sa.Text(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('records_count', sa.Integer(), nullable=False),
    sa.Column('source_type', sa.Text(), nullable=False),
    sa.Column('trigger', sa.Text(), nullable=False),
    sa.CheckConstraint("status IN ('running', 'success', 'failed', 'partial')", name='ck_sync_jobs_status'),
    sa.ForeignKeyConstraint(['service_id'], ['ai_services.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sync_jobs_service_started', 'sync_jobs', ['service_id', 'started_at'], unique=False)
    op.create_table('usage_snapshots',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('service_id', sa.Text(), nullable=False),
    sa.Column('metric_code', sa.Text(), nullable=False),
    sa.Column('used_value', sa.Numeric(), nullable=True),
    sa.Column('limit_value', sa.Numeric(), nullable=True),
    sa.Column('unit', sa.Text(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=True),
    sa.Column('period_end', sa.Date(), nullable=True),
    sa.Column('resets_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_type', sa.Text(), nullable=False),
    sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('raw', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.CheckConstraint("source_type IN ('api', 'cli', 'manual')", name='ck_usage_snapshots_source'),
    sa.CheckConstraint("status IN ('ok', 'unavailable')", name='ck_usage_snapshots_status'),
    sa.ForeignKeyConstraint(['service_id'], ['ai_services.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_usage_snapshots_service_captured', 'usage_snapshots', ['service_id', 'captured_at'], unique=False)
    op.create_table('user_settings',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('timezone', sa.Text(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('alert_threshold', sa.Integer(), nullable=False),
    sa.Column('fx_usd_krw', sa.Numeric(precision=10, scale=4), nullable=True),
    sa.Column('fx_rate_date', sa.Date(), nullable=True),
    sa.Column('sync_interval_minutes', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )


def downgrade() -> None:
    op.drop_table('user_settings')
    op.drop_index('ix_usage_snapshots_service_captured', table_name='usage_snapshots')
    op.drop_table('usage_snapshots')
    op.drop_index('ix_sync_jobs_service_started', table_name='sync_jobs')
    op.drop_table('sync_jobs')
    op.drop_table('subscriptions')
    op.drop_table('service_credentials')
    op.drop_index('ix_cost_records_period', table_name='cost_records')
    op.drop_table('cost_records')
    op.drop_table('users')
    op.drop_table('ai_services')
