"""manual forward channel backfill

Revision ID: u3h4c5d6e7f8
Revises: t2g3b4c5d6e7
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa


revision = "u3h4c5d6e7f8"
down_revision = "t2g3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_manual_backfill_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("owner_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("delivery_mode", sa.String(length=16), nullable=False),
        sa.Column("instruction_status", sa.String(length=32), nullable=False),
        sa.Column("instruction_message_id", sa.BigInteger(), nullable=True),
        sa.Column("requested_limit", sa.Integer(), nullable=False),
        sa.Column("received_messages", sa.Integer(), nullable=False),
        sa.Column("received_publications", sa.Integer(), nullable=False),
        sa.Column("rejected_messages", sa.Integer(), nullable=False),
        sa.Column("imported_publications", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["channel_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_channel_manual_backfill_claim",
        "channel_manual_backfill_sessions",
        ["status", "available_at", "locked_until"],
        unique=False,
    )
    op.create_index(
        "ix_channel_manual_backfill_shop_status",
        "channel_manual_backfill_sessions",
        ["shop_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_channel_manual_backfill_sessions_connection_id"),
        "channel_manual_backfill_sessions",
        ["connection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_channel_manual_backfill_sessions_shop_id"),
        "channel_manual_backfill_sessions",
        ["shop_id"],
        unique=False,
    )

    op.create_table(
        "channel_manual_backfill_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("source_message_id", sa.BigInteger(), nullable=False),
        sa.Column("source_media_group_id", sa.String(length=255), nullable=True),
        sa.Column("group_key", sa.String(length=320), nullable=False),
        sa.Column("destination_message_id", sa.BigInteger(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("media", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["channel_manual_backfill_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "source_message_id",
            name="uq_channel_manual_backfill_source",
        ),
    )
    op.create_index(
        "ix_channel_manual_backfill_item_group",
        "channel_manual_backfill_items",
        ["session_id", "group_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_channel_manual_backfill_items_session_id"),
        "channel_manual_backfill_items",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_channel_manual_backfill_items_session_id"),
        table_name="channel_manual_backfill_items",
    )
    op.drop_index(
        "ix_channel_manual_backfill_item_group",
        table_name="channel_manual_backfill_items",
    )
    op.drop_table("channel_manual_backfill_items")
    op.drop_index(
        op.f("ix_channel_manual_backfill_sessions_shop_id"),
        table_name="channel_manual_backfill_sessions",
    )
    op.drop_index(
        op.f("ix_channel_manual_backfill_sessions_connection_id"),
        table_name="channel_manual_backfill_sessions",
    )
    op.drop_index(
        "ix_channel_manual_backfill_shop_status",
        table_name="channel_manual_backfill_sessions",
    )
    op.drop_index(
        "ix_channel_manual_backfill_claim",
        table_name="channel_manual_backfill_sessions",
    )
    op.drop_table("channel_manual_backfill_sessions")
