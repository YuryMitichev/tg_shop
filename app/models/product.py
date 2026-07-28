from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))

    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)

    category: Mapped["Category"] = relationship(back_populates="products")

    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product",
        order_by="ProductVariant.id",
        cascade="all, delete-orphan",
    )

    photos: Mapped[list["ProductPhoto"]] = relationship(
        back_populates="product",
        order_by="ProductPhoto.position",
        cascade="all, delete-orphan",
    )
