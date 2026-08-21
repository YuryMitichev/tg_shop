from datetime import datetime

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "telegram_user_id",
            "product_id",
            name="uq_favorites_shop_user_product",
        ),
        ForeignKeyConstraint(
            ["product_id", "shop_id"],
            ["products.id", "products.shop_id"],
            name="fk_favorites_product_tenant",
            ondelete="CASCADE",
        ),
        Index(
            "ix_favorites_shop_user_created",
            "shop_id",
            "telegram_user_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), nullable=False
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_id: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
