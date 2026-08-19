"""channel publication attribution

Revision ID: q9d0e1f2a3b4
Revises: p8c9d0e1f2a3
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa


revision = "q9d0e1f2a3b4"
down_revision = "p8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_source_refs", sa.Column("public_token", sa.String(length=32), nullable=True)
    )
    op.execute("UPDATE product_source_refs SET public_token = 'r' || id::text")
    op.alter_column("product_source_refs", "public_token", nullable=False)
    op.create_index(
        "ix_product_source_refs_public_token",
        "product_source_refs",
        ["public_token"],
        unique=True,
    )

    op.add_column("channel_posts", sa.Column("telegram_views", sa.Integer(), nullable=True))
    op.add_column("channel_posts", sa.Column("telegram_forwards", sa.Integer(), nullable=True))
    op.add_column("channel_posts", sa.Column("metrics_updated_at", sa.DateTime(), nullable=True))

    for table in ("cart_items", "order_items"):
        op.add_column(table, sa.Column("source_ref_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("source_post_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_source_ref_id",
            table,
            "product_source_refs",
            ["source_ref_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            f"fk_{table}_source_post_id",
            table,
            "channel_posts",
            ["source_post_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_{table}_source_post_id", table, ["source_post_id"])

    op.create_table(
        "channel_attribution_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("event_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["channel_posts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_ref_id"], ["product_source_refs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shop_id", "event_type", "event_key", name="uq_channel_attribution_event_key"
        ),
    )
    op.create_index(
        "ix_channel_attribution_post_event",
        "channel_attribution_events",
        ["shop_id", "post_id", "event_type"],
    )
    op.create_index(
        "ix_channel_attribution_events_shop_id", "channel_attribution_events", ["shop_id"]
    )
    op.create_index(
        "ix_channel_attribution_events_post_id", "channel_attribution_events", ["post_id"]
    )
    op.create_index(
        "ix_channel_attribution_events_source_ref_id",
        "channel_attribution_events",
        ["source_ref_id"],
    )
    op.create_index(
        "ix_channel_attribution_events_product_id",
        "channel_attribution_events",
        ["product_id"],
    )
    op.create_index(
        "ix_channel_attribution_events_telegram_user_id",
        "channel_attribution_events",
        ["telegram_user_id"],
    )


def downgrade() -> None:
    op.drop_table("channel_attribution_events")
    for table in ("order_items", "cart_items"):
        op.drop_index(f"ix_{table}_source_post_id", table_name=table)
        op.drop_constraint(f"fk_{table}_source_post_id", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_source_ref_id", table, type_="foreignkey")
        op.drop_column(table, "source_post_id")
        op.drop_column(table, "source_ref_id")
    op.drop_column("channel_posts", "metrics_updated_at")
    op.drop_column("channel_posts", "telegram_forwards")
    op.drop_column("channel_posts", "telegram_views")
    op.drop_index("ix_product_source_refs_public_token", table_name="product_source_refs")
    op.drop_column("product_source_refs", "public_token")
