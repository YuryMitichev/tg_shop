from sqlalchemy import select, exists
from sqlalchemy.orm import selectinload

from app.database.db import async_session
from app.models.order import Order
from app.models.order_item import OrderItem
from app.services.cart_service import CartService
from app.services.offer_service import OfferService
from app.services.promo_service import PromoCodeService


class OrderService:

    @staticmethod
    async def create_order(
        telegram_user_id: int,
        full_name: str,
        phone: str,
        address: str,
        comment: str | None = None,
        promo_code: str | None = None,
    ) -> dict | None:
        """
        Создаёт заказ из текущей корзины пользователя и очищает корзину.

        Возвращает None, если корзина пуста.
        """
        items = await CartService.get_items(telegram_user_id)

        if not items:
            return None

        total = sum(item["subtotal"] for item in items)

        discount = 0
        applied_promo = None

        if promo_code:
            promo_info = await PromoCodeService.validate(promo_code, total)

            if promo_info:
                discount = promo_info["discount_amount"]
                applied_promo = promo_info["code"]

        final_total = total - discount

        async with async_session() as session:
            order = Order(
                telegram_user_id=telegram_user_id,
                status="new",
                full_name=full_name,
                phone=phone,
                address=address,
                comment=comment,
                total_amount=final_total,
                promo_code=applied_promo,
                discount_amount=discount,
            )

            order.items = [
                OrderItem(
                    product_name=item["product_name"],
                    product_id=item["product_id"],
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

        for item in items:
            if item.get("discount_percent", 0) > 0:
                await OfferService.mark_used(
                    telegram_user_id, item["product_id"], item["variant_id"]
                )

        if applied_promo:
            await PromoCodeService.increment_usage(applied_promo)

        return {
            "order_id": order_id,
            "items": items,
            "total": final_total,
            "subtotal": total,
            "discount": discount,
            "promo_code": applied_promo,
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
    async def has_purchased(telegram_user_id: int, product_id: int) -> bool:
        """Проверяет, покупал ли пользователь данный товар (заказ не отменён)."""
        async with async_session() as session:
            result = await session.execute(
                select(
                    exists()
                    .where(
                        OrderItem.product_id == product_id,
                        OrderItem.order_id == Order.id,
                        Order.telegram_user_id == telegram_user_id,
                        Order.status != "cancelled",
                    )
                )
            )
            return bool(result.scalar())

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
