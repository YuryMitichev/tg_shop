from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class ProductAttributeDef(Base):
    """Определение характеристики товара для конкретного магазина.

    Каждый магазин может создавать произвольные характеристики
    (цвет, аромат, вес и т.д.). Значения характеристик хранятся
    в ProductVariant.attributes (JSON).
    """

    __tablename__ = "product_attribute_defs"
    __table_args__ = (
        UniqueConstraint("shop_id", "key", name="uq_product_attr_defs_shop_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True)

    key: Mapped[str] = mapped_column(nullable=False)

    label: Mapped[str] = mapped_column(nullable=False)

    position: Mapped[int] = mapped_column(default=0, nullable=False)

    is_required: Mapped[bool] = mapped_column(default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
