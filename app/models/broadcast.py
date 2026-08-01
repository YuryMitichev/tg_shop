from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)

    product_id: Mapped[int] = mapped_column(nullable=False)

    product_name: Mapped[str] = mapped_column(nullable=False)

    variant_id: Mapped[int | None] = mapped_column(nullable=True)

    variant_volume: Mapped[str | None] = mapped_column(nullable=True)

    original_price: Mapped[int] = mapped_column(nullable=False)

    discount_percent: Mapped[int] = mapped_column(default=0)

    discounted_price: Mapped[int] = mapped_column(nullable=False)

    message_text: Mapped[str | None] = mapped_column(nullable=True)

    filter_tags: Mapped[str | None] = mapped_column(nullable=True)

    status: Mapped[str] = mapped_column(default="draft")

    recipients_count: Mapped[int] = mapped_column(default=0)

    sent_count: Mapped[int] = mapped_column(default=0)

    failed_count: Mapped[int] = mapped_column(default=0)

    created_by: Mapped[int | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
