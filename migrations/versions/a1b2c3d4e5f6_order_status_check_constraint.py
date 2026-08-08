"""order status check constraint

Revision ID: a1b2c3d4e5f6
Revises: f2b1a3c4d5e6
Create Date: 2026-08-04 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f2b1a3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VALID_STATUSES = [
    'new', 'confirmed', 'paid', 'shipped', 'done', 'cancelled',
]


def upgrade() -> None:
    with op.batch_alter_table('orders') as batch_op:
        batch_op.create_check_constraint(
            'ck_orders_status',
            f"status IN ({', '.join(repr(s) for s in VALID_STATUSES)})",
        )


def downgrade() -> None:
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_constraint('ck_orders_status', type_='check')
