"""channel product buttons

Revision ID: n6a7b8c9d0e1
Revises: m5f6a7b8c9d0
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa


revision = "n6a7b8c9d0e1"
down_revision = "m5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channel_posts", sa.Column("source_reply_markup", sa.JSON(), nullable=True))
    op.add_column(
        "channel_posts",
        sa.Column("source_reply_markup_known", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "channel_posts",
        sa.Column("button_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "product_source_refs",
        sa.Column("source_kind", sa.String(length=16), nullable=False, server_default="ai"),
    )
    op.add_column(
        "product_source_refs",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "channel_post_button_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("button_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["post_id"], ["channel_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "button_version", name="uq_channel_button_jobs_version"),
    )
    op.create_index(
        "ix_channel_button_jobs_claim",
        "channel_post_button_jobs",
        ["status", "available_at", "locked_until"],
    )
    op.create_index("ix_channel_post_button_jobs_post_id", "channel_post_button_jobs", ["post_id"])
    op.create_index("ix_channel_post_button_jobs_shop_id", "channel_post_button_jobs", ["shop_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_post_button_jobs_shop_id", table_name="channel_post_button_jobs")
    op.drop_index("ix_channel_post_button_jobs_post_id", table_name="channel_post_button_jobs")
    op.drop_index("ix_channel_button_jobs_claim", table_name="channel_post_button_jobs")
    op.drop_table("channel_post_button_jobs")
    op.drop_column("product_source_refs", "updated_at")
    op.drop_column("product_source_refs", "source_kind")
    op.drop_column("channel_posts", "button_version")
    op.drop_column("channel_posts", "source_reply_markup_known")
    op.drop_column("channel_posts", "source_reply_markup")
