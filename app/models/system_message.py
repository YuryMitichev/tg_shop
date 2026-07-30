from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class SystemMessage(Base):
    __tablename__ = "system_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(unique=True, nullable=False)
    content: Mapped[str] = mapped_column(nullable=False)
