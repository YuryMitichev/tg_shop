from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(nullable=False)

    bot_token: Mapped[str] = mapped_column(unique=True, nullable=False)

    owner_telegram_id: Mapped[int] = mapped_column(nullable=False)

    is_active: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
