from datetime import datetime

from sqlalchemy import ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("order_id", "attempt", name="uq_payments_order_attempt"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)

    # yookassa | tinkoff
    provider: Mapped[str] = mapped_column(default="yookassa")

    # Номер попытки оплаты заказа: 1, 2, ... Retry той же попытки
    # не инкрементирует счётчик; новая попытка после canceled — да.
    attempt: Mapped[int] = mapped_column(nullable=False, default=1)

    # ID платежа у провайдера
    provider_payment_id: Mapped[str | None] = mapped_column(
        nullable=True, index=True, unique=True
    )

    # Детерминированный ключ идемпотентности одной попытки:
    # order:{order_id}:yookassa (попытка 1), order:{order_id}:yookassa:{n}
    idempotency_key: Mapped[str] = mapped_column(nullable=False, unique=True)

    # Сумма в минорных единицах (копейках)
    amount_minor: Mapped[int] = mapped_column(nullable=False)

    currency: Mapped[str] = mapped_column(default="RUB")

    # pending | succeeded | canceled
    status: Mapped[str] = mapped_column(default="pending")

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
