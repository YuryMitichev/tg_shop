"""add promo_codes table and order promo fields

Revision ID: a3b8c9d0e1f2
Revises: f2a7b8c9d0e1
Create Date: 2026-07-30 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f2a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('promo_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('discount_type', sa.String(), nullable=False),
        sa.Column('discount_value', sa.Integer(), nullable=False),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('used_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index('ix_promo_codes_code', 'promo_codes', ['code'])

    op.add_column('orders', sa.Column('promo_code', sa.String(), nullable=True))
    op.add_column('orders', sa.Column('discount_amount', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('orders', 'discount_amount')
    op.drop_column('orders', 'promo_code')
    op.drop_index('ix_promo_codes_code', table_name='promo_codes')
    op.drop_table('promo_codes')
