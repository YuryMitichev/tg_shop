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
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))

    # product_id добавлен для проверки покупки при отзывах.
    # nullable: старые заказы (до миграции) не содержат это поле.
    product_id: Mapped[int | None] = mapped_column(nullable=True)

    # variant_id нужен для возврата остатка при отмене заказа.
    # nullable: старые заказы (до миграции) не содержат это поле.
    variant_id: Mapped[int | None] = mapped_column(nullable=True)

    product_name: Mapped[str] = mapped_column(nullable=False)
    variant_volume: Mapped[str] = mapped_column(nullable=False)
    price: Mapped[int] = mapped_column(nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")
