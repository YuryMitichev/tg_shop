"""channel storefront pinned message

Revision ID: o7b8c9d0e1f2
Revises: n6a7b8c9d0e1
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa


revision = "o7b8c9d0e1f2"
down_revision = "n6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channel_connections",
        sa.Column("storefront_message_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "channel_connections",
        sa.Column(
            "storefront_status",
            sa.String(length=32),
            nullable=False,
            server_default="not_created",
        ),
    )
    op.add_column(
        "channel_connections",
        sa.Column("storefront_error_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "channel_connections",
        sa.Column("storefront_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "channel_connections",
        sa.Column("storefront_updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("channel_connections", "storefront_updated_at")
    op.drop_column("channel_connections", "storefront_error")
    op.drop_column("channel_connections", "storefront_error_code")
    op.drop_column("channel_connections", "storefront_status")
    op.drop_column("channel_connections", "storefront_message_id")
