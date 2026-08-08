from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class OfferAcceptance(Base):
    """Запись о принятии публичной оферты пользователем платформы."""

    __tablename__ = "offer_acceptances"

    id: Mapped[int] = mapped_column(primary_key=True)

    telegram_user_id: Mapped[int] = mapped_column(index=True)

    full_name: Mapped[str | None] = mapped_column(nullable=True)

    username: Mapped[str | None] = mapped_column(nullable=True)

    offer_version: Mapped[str] = mapped_column(nullable=False)

    accepted_at: Mapped[datetime] = mapped_column(server_default=func.now())
