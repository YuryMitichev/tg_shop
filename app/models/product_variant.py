from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))

    volume: Mapped[str] = mapped_column(nullable=False)
    price: Mapped[int] = mapped_column(nullable=False)
    burn: Mapped[str | None] = mapped_column(nullable=True)
    photo: Mapped[str | None] = mapped_column(nullable=True)
    stock: Mapped[int] = mapped_column(default=0, nullable=False)

    size: Mapped[str | None] = mapped_column(nullable=True)
    color: Mapped[str | None] = mapped_column(nullable=True)
    scent: Mapped[str | None] = mapped_column(nullable=True)
    dimensions: Mapped[str | None] = mapped_column(nullable=True)

    product: Mapped["Product"] = relationship(back_populates="variants")
