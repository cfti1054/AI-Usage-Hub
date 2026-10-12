"""fx auto refresh: fx_mode, fx_source, fx_updated_at

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('user_settings') as batch:
        batch.add_column(sa.Column('fx_mode', sa.Text(), server_default='auto', nullable=False))
        batch.add_column(sa.Column('fx_source', sa.Text(), nullable=True))
        batch.add_column(sa.Column('fx_updated_at', sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint('ck_user_settings_fx_mode', "fx_mode IN ('auto', 'manual')")
    # 이미 직접 입력한 환율이 있으면 덮어쓰지 않도록 수동 모드로 둔다
    op.execute("UPDATE user_settings SET fx_mode = 'manual', fx_source = 'manual' WHERE fx_usd_krw IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table('user_settings') as batch:
        batch.drop_constraint('ck_user_settings_fx_mode', type_='check')
        batch.drop_column('fx_updated_at')
        batch.drop_column('fx_source')
        batch.drop_column('fx_mode')
