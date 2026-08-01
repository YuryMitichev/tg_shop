from datetime import datetime

from sqlalchemy import func, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class PromoCode(Base):
    __tablename__ = "promo_codes"
    __table_args__ = (
        UniqueConstraint("shop_id", "code", name="uq_promo_shop_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)

    code: Mapped[str] = mapped_column(index=True)

    # "percent" или "fixed"
    discount_type: Mapped[str] = mapped_column(default="percent")

    # Для percent: 10 = 10%. Для fixed: 500 = 500₽
    discount_value: Mapped[int] = mapped_column(nullable=False)

    max_uses: Mapped[int | None] = mapped_column(nullable=True)
    used_count: Mapped[int] = mapped_column(default=0)

    is_active: Mapped[bool] = mapped_column(default=True)

    valid_until: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
