from datetime import datetime

from sqlalchemy import func, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        UniqueConstraint("shop_id", "telegram_user_id", name="uq_profile_shop_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)

    telegram_user_id: Mapped[int] = mapped_column(index=True)

    username: Mapped[str | None] = mapped_column(nullable=True)

    first_name: Mapped[str | None] = mapped_column(nullable=True)

    last_name: Mapped[str | None] = mapped_column(nullable=True)

    phone: Mapped[str | None] = mapped_column(nullable=True)

    notes: Mapped[str | None] = mapped_column(nullable=True)

    tags: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    last_seen: Mapped[datetime | None] = mapped_column(nullable=True)
