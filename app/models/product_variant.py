from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database.db import Base


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))

    volume: Mapped[str] = mapped_column(nullable=False)
    price: Mapped[int] = mapped_column(nullable=False)
    photo: Mapped[str | None] = mapped_column(nullable=True)
    stock: Mapped[int] = mapped_column(default=0, nullable=False)

    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="variants")
