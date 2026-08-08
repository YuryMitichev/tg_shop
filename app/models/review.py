from datetime import datetime

from sqlalchemy import func, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("product_id", "telegram_user_id", name="uq_review_product_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)

    product_id: Mapped[int] = mapped_column(index=True)

    telegram_user_id: Mapped[int] = mapped_column(index=True)

    rating: Mapped[int] = mapped_column(nullable=False)

    text: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
