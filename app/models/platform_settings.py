from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    yookassa_shop_id: Mapped[str | None] = mapped_column(nullable=True)

    yookassa_secret_key: Mapped[str | None] = mapped_column(nullable=True)

    yookassa_enabled: Mapped[bool] = mapped_column(default=False)

    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
