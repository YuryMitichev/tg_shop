from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.db import async_session
from app.models.order import Order
from app.models.order_item import OrderItem
from app.services.cart_service import CartService


class OrderService:

    @staticmethod
    async def create_order(
        telegram_user_id: int,
        full_name: str,
        phone: str,
        address: str,
        comment: str | None = None,
    ) -> dict | None:
        """
        Создаёт заказ из текущей корзины пользователя и очищает корзину.

        Возвращает None, если корзина пуста.
        """
        items = await CartService.get_items(telegram_user_id)

        if not items:
            return None

        total = sum(item["subtotal"] for item in items)

        async with async_session() as session:
            order = Order(
                telegram_user_id=telegram_user_id,
                status="new",
                full_name=full_name,
                phone=phone,
                address=address,
                comment=comment,
                total_amount=total,
            )

            order.items = [
                OrderItem(
                    product_name=item["product_name"],
                    variant_volume=item["volume"],
                    price=item["price"],
                    quantity=item["quantity"],
                )
                for item in items
            ]

            session.add(order)
            await session.commit()
            await session.refresh(order)

            order_id = order.id

        await CartService.clear(telegram_user_id)

        return {
            "order_id": order_id,
            "items": items,
            "total": total,
            "full_name": full_name,
            "phone": phone,
            "address": address,
            "comment": comment,
        }

    @staticmethod
    async def get_order_owner(order_id: int) -> int | None:
        """Возвращает telegram_user_id владельца заказа."""
        async with async_session() as session:
            result = await session.execute(
                select(Order.telegram_user_id).where(Order.id == order_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_user_orders(telegram_user_id: int, limit: int = 10) -> list[dict]:
        """Последние заказы пользователя (краткая информация)."""
        async with async_session() as session:
            result = await session.execute(
                select(Order)
                .where(Order.telegram_user_id == telegram_user_id)
                .order_by(Order.id.desc())
                .limit(limit)
            )
            return [
                {
                    "id": order.id,
                    "status": order.status,
                    "total_amount": order.total_amount,
                    "created_at": order.created_at,
                }
                for order in result.scalars().all()
            ]

    @staticmethod
    async def get_user_order(
        telegram_user_id: int,
        order_id: int,
    ) -> dict | None:
        """Детальная информация о заказе пользователя."""
        async with async_session() as session:
            result = await session.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(
                    Order.id == order_id,
                    Order.telegram_user_id == telegram_user_id,
                )
            )
            order = result.scalar_one_or_none()

            if not order:
                return None

            return {
                "id": order.id,
                "status": order.status,
                "full_name": order.full_name,
                "phone": order.phone,
                "address": order.address,
                "comment": order.comment,
                "total_amount": order.total_amount,
                "created_at": order.created_at,
                "items": [
                    {
                        "product_name": item.product_name,
                        "variant_volume": item.variant_volume,
                        "price": item.price,
                        "quantity": item.quantity,
                    }
                    for item in order.items
                ],
            }
