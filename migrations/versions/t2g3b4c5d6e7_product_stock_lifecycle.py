"""product stock lifecycle

Revision ID: t2g3b4c5d6e7
Revises: s1f2a3b4c5d6
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa


revision = "t2g3b4c5d6e7"
down_revision = "s1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products", sa.Column("out_of_stock_since", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "products", sa.Column("auto_hidden_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "products", sa.Column("lifecycle_deleted_at", sa.DateTime(), nullable=True)
    )
    op.create_index(
        "ix_products_lifecycle_scan",
        "products",
        ["lifecycle_deleted_at", "out_of_stock_since"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_products_lifecycle_scan", table_name="products")
    op.drop_column("products", "lifecycle_deleted_at")
    op.drop_column("products", "auto_hidden_at")
    op.drop_column("products", "out_of_stock_since")
