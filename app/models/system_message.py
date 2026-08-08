from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class SystemMessage(Base):
    __tablename__ = "system_messages"
    __table_args__ = (
        UniqueConstraint("shop_id", "key", name="uq_system_message_shop_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)
    key: Mapped[str] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(nullable=False)
