from datetime import datetime

from sqlalchemy import func, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class AdminUser(Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        UniqueConstraint("shop_id", "telegram_user_id", name="uq_admin_shop_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)

    telegram_user_id: Mapped[int] = mapped_column(index=True)

    display_name: Mapped[str | None] = mapped_column(nullable=True)

    role: Mapped[str] = mapped_column(default="manager", nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
