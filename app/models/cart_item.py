from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class CartItem(Base):
    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    telegram_user_id: Mapped[int] = mapped_column(index=True)

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))

    quantity: Mapped[int] = mapped_column(default=1)
