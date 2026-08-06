"""offer acceptance table

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-08-06 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd6e7f8a9b0c1'
down_revision: Union[str, Sequence[str], None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "offer_acceptances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("offer_version", sa.String(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_offer_acceptances_telegram_user_id", "offer_acceptances", ["telegram_user_id"])


def downgrade() -> None:
    op.drop_index("ix_offer_acceptances_telegram_user_id", table_name="offer_acceptances")
    op.drop_table("offer_acceptances")
