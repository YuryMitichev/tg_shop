from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class UserOffer(Base):
    __tablename__ = "user_offers"

    id: Mapped[int] = mapped_column(primary_key=True)

    telegram_user_id: Mapped[int] = mapped_column(index=True)

    product_id: Mapped[int] = mapped_column(index=True)

    variant_id: Mapped[int | None] = mapped_column(nullable=True)

    discount_percent: Mapped[int] = mapped_column(nullable=False)

    broadcast_id: Mapped[int | None] = mapped_column(nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
