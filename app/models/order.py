from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)

    telegram_user_id: Mapped[int] = mapped_column(index=True)

    # new -> confirmed -> paid -> shipped -> done (или cancelled)
    status: Mapped[str] = mapped_column(default="new")

    full_name: Mapped[str] = mapped_column(nullable=False)
    phone: Mapped[str] = mapped_column(nullable=False)
    address: Mapped[str] = mapped_column(nullable=False)
    comment: Mapped[str | None] = mapped_column(nullable=True)

    total_amount: Mapped[int] = mapped_column(nullable=False)

    # Промокод и размер скидки
    promo_code: Mapped[str | None] = mapped_column(nullable=True)
    discount_amount: Mapped[int] = mapped_column(default=0)

    # ID платежа во внешней системе (ЮKassa / Тинькофф)
    payment_id: Mapped[str | None] = mapped_column(nullable=True)

    # manual | yookassa
    payment_method: Mapped[str] = mapped_column(default="manual")

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    status_updated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        order_by="OrderItem.id",
        cascade="all, delete-orphan",
    )
