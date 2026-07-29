from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)

    telegram_user_id: Mapped[int] = mapped_column(index=True)

    # new -> confirmed -> paid -> shipped -> done (или cancelled)
    status: Mapped[str] = mapped_column(default="new")

    full_name: Mapped[str] = mapped_column(nullable=False)
    phone: Mapped[str] = mapped_column(nullable=False)
    address: Mapped[str] = mapped_column(nullable=False)
    comment: Mapped[str | None] = mapped_column(nullable=True)

    total_amount: Mapped[int] = mapped_column(nullable=False)

    # ID платежа в Тинькофф (после Init)
    payment_id: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        order_by="OrderItem.id",
        cascade="all, delete-orphan",
    )
