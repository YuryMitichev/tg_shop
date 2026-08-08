from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)
    name: Mapped[str] = mapped_column(nullable=False)
    emoji: Mapped[str | None] = mapped_column(nullable=True)

    products: Mapped[list["Product"]] = relationship(
        back_populates="category",
        order_by="Product.id",
    )
