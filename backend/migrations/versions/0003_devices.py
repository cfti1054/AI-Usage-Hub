"""devices: 기기 등록과 기기별 사용량

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIG_ID = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')


def upgrade() -> None:
    op.create_table('devices',
    sa.Column('id', BIG_ID, nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash'),
    sa.UniqueConstraint('user_id', 'name', name='uq_devices_user_name')
    )
    with op.batch_alter_table('usage_snapshots') as batch:
        batch.add_column(sa.Column('device_id', BIG_ID, nullable=True))
        batch.create_foreign_key('fk_usage_snapshots_device_id', 'devices', ['device_id'], ['id'])
        batch.create_unique_constraint(
            'uq_usage_snapshots_device_bucket', ['device_id', 'service_id', 'metric_code', 'period_start']
        )


def downgrade() -> None:
    with op.batch_alter_table('usage_snapshots') as batch:
        batch.drop_constraint('uq_usage_snapshots_device_bucket', type_='unique')
        batch.drop_constraint('fk_usage_snapshots_device_id', type_='foreignkey')
        batch.drop_column('device_id')
    op.drop_table('devices')
