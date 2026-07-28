from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class OrderItem(Base):
    """
    Позиция в заказе.

    Название товара, объём и цена сохраняются как снапшот на
    момент заказа — если товар потом изменится или будет удалён
    из каталога, история заказов не пострадает.
    """

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))

    product_name: Mapped[str] = mapped_column(nullable=False)
    variant_volume: Mapped[str] = mapped_column(nullable=False)
    price: Mapped[int] = mapped_column(nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")
