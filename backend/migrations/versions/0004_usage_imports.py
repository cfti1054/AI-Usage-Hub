"""usage imports: CSV 업로드 이력과 요청별 사용량

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('usage_imports',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('service_id', sa.Text(), nullable=False),
    sa.Column('filename', sa.Text(), nullable=False),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('rows_total', sa.Integer(), nullable=False),
    sa.Column('rows_added', sa.Integer(), nullable=False),
    sa.Column('rows_duplicate', sa.Integer(), nullable=False),
    sa.Column('rows_invalid', sa.Integer(), nullable=False),
    sa.Column('period_from', sa.DateTime(timezone=True), nullable=True),
    sa.Column('period_to', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['service_id'], ['ai_services.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('usage_events',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('service_id', sa.Text(), nullable=False),
    sa.Column('import_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('model', sa.Text(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=True),
    sa.Column('input_tokens', sa.BigInteger(), nullable=False),
    sa.Column('output_tokens', sa.BigInteger(), nullable=False),
    sa.Column('cache_creation_tokens', sa.BigInteger(), nullable=False),
    sa.Column('cache_read_tokens', sa.BigInteger(), nullable=False),
    sa.Column('total_tokens', sa.BigInteger(), nullable=False),
    sa.Column('cost_usd', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.ForeignKeyConstraint(['import_id'], ['usage_imports.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['service_id'], ['ai_services.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'service_id', 'occurred_at', 'model', 'total_tokens', name='uq_usage_events_identity')
    )
    op.create_index('ix_usage_events_service_time', 'usage_events', ['service_id', 'occurred_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_usage_events_service_time', table_name='usage_events')
    op.drop_table('usage_events')
    op.drop_table('usage_imports')
