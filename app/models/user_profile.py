from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)

    telegram_user_id: Mapped[int] = mapped_column(unique=True, index=True)

    username: Mapped[str | None] = mapped_column(nullable=True)

    first_name: Mapped[str | None] = mapped_column(nullable=True)

    last_name: Mapped[str | None] = mapped_column(nullable=True)

    phone: Mapped[str | None] = mapped_column(nullable=True)

    notes: Mapped[str | None] = mapped_column(nullable=True)

    tags: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    last_seen: Mapped[datetime | None] = mapped_column(nullable=True)
