"""per-shop offer and privacy policy

Revision ID: e8a9b0c1d2e3
Revises: d6e7f8a9b0c1
Create Date: 2026-08-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8a9b0c1d2e3'
down_revision: Union[str, Sequence[str], None] = 'd6e7f8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shops") as batch_op:
        batch_op.add_column(sa.Column("offer_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("privacy_policy_text", sa.Text(), nullable=True))

    op.create_table(
        "shop_offer_acceptances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_shop_offer_acceptances_shop_id", "shop_offer_acceptances", ["shop_id"])
    op.create_index("ix_shop_offer_acceptances_telegram_user_id", "shop_offer_acceptances", ["telegram_user_id"])


def downgrade() -> None:
    op.drop_index("ix_shop_offer_acceptances_telegram_user_id", table_name="shop_offer_acceptances")
    op.drop_index("ix_shop_offer_acceptances_shop_id", table_name="shop_offer_acceptances")
    op.drop_table("shop_offer_acceptances")

    with op.batch_alter_table("shops") as batch_op:
        batch_op.drop_column("privacy_policy_text")
        batch_op.drop_column("offer_text")
