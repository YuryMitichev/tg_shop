from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database.db import Base


class ChannelConnection(Base):
    __tablename__ = "channel_connections"
    __table_args__ = (
        UniqueConstraint("shop_id", name="uq_channel_connections_shop"),
        UniqueConstraint("channel_id", name="uq_channel_connections_channel"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_title: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_username: Mapped[str | None] = mapped_column(String(255))
    connected_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    backfill_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    backfill_error: Mapped[str | None] = mapped_column(Text)
    storefront_message_id: Mapped[int | None] = mapped_column(BigInteger)
    storefront_status: Mapped[str] = mapped_column(
        String(32), default="not_created", nullable=False
    )
    storefront_error_code: Mapped[str | None] = mapped_column(String(64))
    storefront_error: Mapped[str | None] = mapped_column(Text)
    storefront_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChannelPost(Base):
    __tablename__ = "channel_posts"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "telegram_message_id", name="uq_channel_posts_source"
        ),
        Index("ix_channel_posts_shop_status", "shop_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("channel_connections.id", ondelete="CASCADE"), index=True
    )
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_group_id: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="received", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime)
    raw_data: Mapped[dict | None] = mapped_column(JSON)
    source_reply_markup: Mapped[dict | None] = mapped_column(JSON)
    source_reply_markup_known: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    button_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChannelPostMedia(Base):
    __tablename__ = "channel_post_media"
    __table_args__ = (
        UniqueConstraint("post_id", "position", name="uq_channel_post_media_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("channel_posts.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[str] = mapped_column(Text, nullable=False)
    file_unique_id: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(32), default="photo", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class CatalogImportJob(Base):
    __tablename__ = "catalog_import_jobs"
    __table_args__ = (
        UniqueConstraint("post_id", "post_version", name="uq_catalog_import_jobs_version"),
        Index("ix_catalog_import_jobs_claim", "status", "available_at", "locked_until"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("channel_posts.id", ondelete="CASCADE"), index=True)
    post_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(128))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CatalogImportCandidate(Base):
    __tablename__ = "catalog_import_candidates"
    __table_args__ = (
        UniqueConstraint("job_id", "position", name="uq_catalog_import_candidates_position"),
        Index("ix_catalog_import_candidates_shop_status", "shop_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("catalog_import_jobs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    name: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    category_name: Mapped[str | None] = mapped_column(String(255))
    proposed_category: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(255))
    currency: Mapped[str | None] = mapped_column(String(8), default="RUB")
    variants: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    field_confidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    duplicate_product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    duplicate_score: Mapped[float | None] = mapped_column(Float)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    owner_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CatalogAnalysisRun(Base):
    __tablename__ = "catalog_analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("catalog_import_jobs.id", ondelete="CASCADE"), index=True)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    prefilter_version: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    result: Mapped[dict | None] = mapped_column(JSON)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_microusd: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class ProductSourceRef(Base):
    __tablename__ = "product_source_refs"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "telegram_message_id",
            "candidate_position",
            name="uq_product_source_refs_source",
        ),
        Index("ix_product_source_refs_shop_sku", "shop_id", "sku"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("channel_connections.id", ondelete="CASCADE"))
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    candidate_position: Mapped[int] = mapped_column(Integer, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(255))
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    source_kind: Mapped[str] = mapped_column(String(16), default="ai", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChannelPostButtonJob(Base):
    __tablename__ = "channel_post_button_jobs"
    __table_args__ = (
        UniqueConstraint("post_id", "button_version", name="uq_channel_button_jobs_version"),
        Index(
            "ix_channel_button_jobs_claim",
            "status",
            "available_at",
            "locked_until",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("channel_posts.id", ondelete="CASCADE"), index=True)
    button_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(128))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PrefilterFeedback(Base):
    __tablename__ = "prefilter_feedback"
    __table_args__ = (
        UniqueConstraint("post_id", name="uq_prefilter_feedback_post"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("channel_posts.id", ondelete="CASCADE"), index=True)
    prefilter_label: Mapped[str] = mapped_column(String(32), nullable=False)
    prefilter_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    owner_label: Mapped[str | None] = mapped_column(String(32))
    features: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
