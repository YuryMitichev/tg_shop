"""product favorites

Revision ID: s1f2a3b4c5d6
Revises: r0e1f2a3b4c5
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa


revision = "s1f2a3b4c5d6"
down_revision = "r0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "favorites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["product_id", "shop_id"],
            ["products.id", "products.shop_id"],
            name="fk_favorites_product_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shop_id",
            "telegram_user_id",
            "product_id",
            name="uq_favorites_shop_user_product",
        ),
    )
    op.create_index(
        "ix_favorites_shop_user_created",
        "favorites",
        ["shop_id", "telegram_user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_favorites_shop_user_created", table_name="favorites")
    op.drop_table("favorites")
