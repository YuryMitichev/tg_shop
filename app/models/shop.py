from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


LEGAL_TYPES = ["individual", "ip", "ooo"]


AVAILABLE_COURIERS = [
    "WB",
    "Ozon",
    "СДЭК",
    "ПЭК",
    "Яндекс Маркет",
    "5Post",
    "Почта России",
]

DEFAULT_ATTR_LABELS = {
    "volume": "Объём",
    "burn": "Время горения",
    "size": "Размер",
    "color": "Цвет",
    "scent": "Аромат",
    "dimensions": "Длина/Ширина/Высота",
}


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(nullable=False)

    bot_token: Mapped[str] = mapped_column(nullable=False)

    bot_token_hash: Mapped[str | None] = mapped_column(unique=True, nullable=True)

    owner_telegram_id: Mapped[int] = mapped_column(nullable=False)

    is_active: Mapped[bool] = mapped_column(default=True)

    delivery_enabled: Mapped[bool] = mapped_column(default=True)

    courier_services: Mapped[str] = mapped_column(default="[]")

    legal_type: Mapped[str] = mapped_column(default="individual")

    company_name: Mapped[str | None] = mapped_column(nullable=True)

    company_inn: Mapped[str | None] = mapped_column(nullable=True)

    company_address: Mapped[str | None] = mapped_column(nullable=True)

    # Per-shop платежные настройки
    payment_card_number: Mapped[str | None] = mapped_column(nullable=True)

    payment_recipient_name: Mapped[str | None] = mapped_column(nullable=True)

    yookassa_shop_id: Mapped[str | None] = mapped_column(nullable=True)

    yookassa_secret_key: Mapped[str | None] = mapped_column(nullable=True)

    yookassa_enabled: Mapped[bool] = mapped_column(default=False)

    manual_payment_enabled: Mapped[bool] = mapped_column(default=True)

    offer_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    privacy_policy_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
