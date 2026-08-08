"""login_tokens table

Revision ID: f2b1a3c4d5e6
Revises: 8c80d770a1a0
Create Date: 2026-08-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2b1a3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '8c80d770a1a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'login_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('telegram_user_id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('is_super_admin', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token', name='uq_login_tokens_token'),
    )
    op.create_index('ix_login_tokens_token', 'login_tokens', ['token'], unique=True)
    op.create_index('ix_login_tokens_telegram_user_id', 'login_tokens', ['telegram_user_id'])
    op.create_index('ix_login_tokens_expires_at', 'login_tokens', ['expires_at'])


def downgrade() -> None:
    op.drop_index('ix_login_tokens_expires_at', table_name='login_tokens')
    op.drop_index('ix_login_tokens_telegram_user_id', table_name='login_tokens')
    op.drop_index('ix_login_tokens_token', table_name='login_tokens')
    op.drop_table('login_tokens')
