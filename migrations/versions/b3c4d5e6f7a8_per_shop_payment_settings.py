"""per-shop payment settings

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-08-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.add_column(sa.Column("payment_card_number", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("payment_recipient_name", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("yookassa_shop_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("yookassa_secret_key", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("yookassa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        batch_op.add_column(sa.Column("manual_payment_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")))


def downgrade() -> None:
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.drop_column("manual_payment_enabled")
        batch_op.drop_column("yookassa_enabled")
        batch_op.drop_column("yookassa_secret_key")
        batch_op.drop_column("yookassa_shop_id")
        batch_op.drop_column("payment_recipient_name")
        batch_op.drop_column("payment_card_number")
