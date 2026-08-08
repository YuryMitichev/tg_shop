from datetime import datetime

from sqlalchemy import func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class CommunicationLog(Base):
    __tablename__ = "communication_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)

    telegram_user_id: Mapped[int] = mapped_column(index=True)

    direction: Mapped[str] = mapped_column(default="in")

    message_type: Mapped[str] = mapped_column(default="text")

    text: Mapped[str | None] = mapped_column(nullable=True)

    admin_id: Mapped[int | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
