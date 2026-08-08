from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class ShopOfferAcceptance(Base):
    """Запись о принятии оферты магазина покупателем."""

    __tablename__ = "shop_offer_acceptances"

    id: Mapped[int] = mapped_column(primary_key=True)

    shop_id: Mapped[int] = mapped_column(index=True)

    telegram_user_id: Mapped[int] = mapped_column(index=True)

    full_name: Mapped[str | None] = mapped_column(nullable=True)

    username: Mapped[str | None] = mapped_column(nullable=True)

    accepted_at: Mapped[datetime] = mapped_column(server_default=func.now())
