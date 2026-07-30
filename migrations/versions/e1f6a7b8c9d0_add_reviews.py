"""add reviews table

Revision ID: e1f6a7b8c9d0
Revises: d0e5f6a7b8c9
Create Date: 2026-07-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd0e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('text', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'telegram_user_id', name='uq_review_product_user'),
    )
    op.create_index('ix_reviews_product_id', 'reviews', ['product_id'])
    op.create_index('ix_reviews_telegram_user_id', 'reviews', ['telegram_user_id'])


def downgrade() -> None:
    op.drop_index('ix_reviews_telegram_user_id', table_name='reviews')
    op.drop_index('ix_reviews_product_id', table_name='reviews')
    op.drop_table('reviews')
