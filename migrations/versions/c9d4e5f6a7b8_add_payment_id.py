"""add payment_id to orders

Revision ID: c9d4e5f6a7b8
Revises: a8b3c4d5e6f7
Create Date: 2026-07-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'a8b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('payment_id', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'payment_id')
