"""add product_id to order_items

Revision ID: f2a7b8c9d0e1
Revises: e1f6a7b8c9d0
Create Date: 2026-07-30 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e1f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('order_items', sa.Column('product_id', sa.Integer(), nullable=True))
    op.create_index('ix_order_items_product_id', 'order_items', ['product_id'])


def downgrade() -> None:
    op.drop_index('ix_order_items_product_id', table_name='order_items')
    op.drop_column('order_items', 'product_id')
