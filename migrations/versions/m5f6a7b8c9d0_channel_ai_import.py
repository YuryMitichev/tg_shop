"""channel AI catalog import

Revision ID: m5f6a7b8c9d0
Revises: l4e5f6a7b8c9
Create Date: 2026-08-19 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "l4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "channel_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_title", sa.String(255), nullable=False),
        sa.Column("channel_username", sa.String(255)),
        sa.Column("connected_by", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("backfill_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("backfill_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("shop_id", name="uq_channel_connections_shop"),
        sa.UniqueConstraint("channel_id", name="uq_channel_connections_channel"),
    )
    op.create_index("ix_channel_connections_shop_id", "channel_connections", ["shop_id"])

    op.create_table(
        "channel_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("channel_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("media_group_id", sa.String(255)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("text", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False, server_default="received"),
        sa.Column("published_at", sa.DateTime()),
        sa.Column("edited_at", sa.DateTime()),
        sa.Column("raw_data", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("connection_id", "telegram_message_id", name="uq_channel_posts_source"),
    )
    op.create_index("ix_channel_posts_shop_id", "channel_posts", ["shop_id"])
    op.create_index("ix_channel_posts_connection_id", "channel_posts", ["connection_id"])
    op.create_index("ix_channel_posts_shop_status", "channel_posts", ["shop_id", "status"])

    op.create_table(
        "channel_post_media",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("channel_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.Text(), nullable=False),
        sa.Column("file_unique_id", sa.String(255)),
        sa.Column("media_type", sa.String(32), nullable=False, server_default="photo"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("post_id", "position", name="uq_channel_post_media_position"),
    )
    op.create_index("ix_channel_post_media_post_id", "channel_post_media", ["post_id"])

    op.create_table(
        "catalog_import_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("channel_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("post_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_by", sa.String(128)),
        sa.Column("locked_until", sa.DateTime()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("post_id", "post_version", name="uq_catalog_import_jobs_version"),
    )
    op.create_index("ix_catalog_import_jobs_shop_id", "catalog_import_jobs", ["shop_id"])
    op.create_index("ix_catalog_import_jobs_post_id", "catalog_import_jobs", ["post_id"])
    op.create_index("ix_catalog_import_jobs_claim", "catalog_import_jobs", ["status", "available_at", "locked_until"])

    op.create_table(
        "catalog_import_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("catalog_import_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("name", sa.String(500)),
        sa.Column("description", sa.Text()),
        sa.Column("category_name", sa.String(255)),
        sa.Column("proposed_category", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sku", sa.String(255)),
        sa.Column("currency", sa.String(8), server_default="RUB"),
        sa.Column("variants", sa.JSON(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("field_confidence", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("duplicate_product_id", sa.Integer(), sa.ForeignKey("products.id")),
        sa.Column("duplicate_score", sa.Float()),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id")),
        sa.Column("owner_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("job_id", "position", name="uq_catalog_import_candidates_position"),
    )
    op.create_index("ix_catalog_import_candidates_shop_id", "catalog_import_candidates", ["shop_id"])
    op.create_index("ix_catalog_import_candidates_job_id", "catalog_import_candidates", ["job_id"])
    op.create_index("ix_catalog_import_candidates_fingerprint", "catalog_import_candidates", ["fingerprint"])
    op.create_index("ix_catalog_import_candidates_shop_status", "catalog_import_candidates", ["shop_id", "status"])

    op.create_table(
        "catalog_analysis_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("catalog_import_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_type", sa.String(32), nullable=False),
        sa.Column("prefilter_version", sa.String(64)),
        sa.Column("prompt_version", sa.String(64)),
        sa.Column("model", sa.String(128)),
        sa.Column("result", sa.JSON()),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_microusd", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_catalog_analysis_runs_shop_id", "catalog_analysis_runs", ["shop_id"])
    op.create_index("ix_catalog_analysis_runs_job_id", "catalog_analysis_runs", ["job_id"])

    op.create_table(
        "product_source_refs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("channel_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("candidate_position", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(255)),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("connection_id", "telegram_message_id", "candidate_position", name="uq_product_source_refs_source"),
    )
    op.create_index("ix_product_source_refs_shop_id", "product_source_refs", ["shop_id"])
    op.create_index("ix_product_source_refs_product_id", "product_source_refs", ["product_id"])
    op.create_index("ix_product_source_refs_fingerprint", "product_source_refs", ["fingerprint"])
    op.create_index("ix_product_source_refs_shop_sku", "product_source_refs", ["shop_id", "sku"])

    op.create_table(
        "prefilter_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("channel_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prefilter_label", sa.String(32), nullable=False),
        sa.Column("prefilter_confidence", sa.Float(), nullable=False),
        sa.Column("owner_label", sa.String(32)),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("post_id", name="uq_prefilter_feedback_post"),
    )
    op.create_index("ix_prefilter_feedback_shop_id", "prefilter_feedback", ["shop_id"])
    op.create_index("ix_prefilter_feedback_post_id", "prefilter_feedback", ["post_id"])


def downgrade() -> None:
    op.drop_table("prefilter_feedback")
    op.drop_table("product_source_refs")
    op.drop_table("catalog_analysis_runs")
    op.drop_table("catalog_import_candidates")
    op.drop_table("catalog_import_jobs")
    op.drop_table("channel_post_media")
    op.drop_table("channel_posts")
    op.drop_table("channel_connections")
