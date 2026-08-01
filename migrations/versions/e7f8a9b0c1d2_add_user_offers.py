"""add user_offers table

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-01 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, Sequence[str], None] = 'd6e7f8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('user_offers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=True),
        sa.Column('discount_percent', sa.Integer(), nullable=False),
        sa.Column('broadcast_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_offers_telegram_user_id', 'user_offers', ['telegram_user_id'])
    op.create_index('ix_user_offers_product_id', 'user_offers', ['product_id'])


def downgrade() -> None:
    op.drop_index('ix_user_offers_product_id', table_name='user_offers')
    op.drop_index('ix_user_offers_telegram_user_id', table_name='user_offers')
    op.drop_table('user_offers')
