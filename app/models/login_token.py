from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class LoginToken(Base):
    __tablename__ = "login_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)

    token: Mapped[str] = mapped_column(unique=True, index=True)

    telegram_user_id: Mapped[int] = mapped_column(index=True)

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))

    is_super_admin: Mapped[bool] = mapped_column(default=False)

    expires_at: Mapped[datetime] = mapped_column(index=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
