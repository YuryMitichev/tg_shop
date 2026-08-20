from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("id", "shop_id", name="uq_products_id_shop"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))

    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    out_of_stock_since: Mapped[datetime | None] = mapped_column(nullable=True)
    auto_hidden_at: Mapped[datetime | None] = mapped_column(nullable=True)
    lifecycle_deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    category: Mapped["Category"] = relationship(back_populates="products")

    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product",
        foreign_keys="[ProductVariant.product_id, ProductVariant.shop_id]",
        order_by="ProductVariant.id",
        cascade="all, delete-orphan",
    )

    photos: Mapped[list["ProductPhoto"]] = relationship(
        back_populates="product",
        order_by="ProductPhoto.position",
        cascade="all, delete-orphan",
    )
