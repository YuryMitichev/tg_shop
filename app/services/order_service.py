from datetime import datetime, timedelta

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.orm import selectinload

from app.core.enums import OrderStatus
from app.database.db import async_session
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.cart_item import CartItem
from app.models.product_variant import ProductVariant
from app.models.shop import Shop
from app.services.cart_service import CartService
from app.services.offer_service import OfferService
from app.services.promo_service import PromoCodeService


class OrderService:

    RESERVATION_MINUTES = 20
    MAX_ACTIVE_UNPAID_PER_USER = 3
    MAX_ACTIVE_UNPAID_PER_SHOP = 200

    @staticmethod
    async def create_order(
        shop_id: int,
        telegram_user_id: int,
        full_name: str,
        phone: str,
        address: str,
        comment: str | None = None,
        promo_code: str | None = None,
        payment_method: str = "manual",
    ) -> dict | None:
        """
        Создаёт заказ из текущей корзины пользователя и очищает корзину.

        Возвращает None, если корзина пуста.
        Возвращает {"error": "out_of_stock", "items": [...]} если товар закончился.
        """
        if payment_method not in {"manual", "yookassa"}:
            return {"error": "invalid_payment_method"}

        items = await CartService.get_items(shop_id, telegram_user_id)

        if not items:
            return None

        if any(item["quantity"] < 1 or item["quantity"] > 100 for item in items):
            return {"error": "invalid_quantity"}
        if any(item["price"] <= 0 or item["subtotal"] <= 0 for item in items):
            return {"error": "invalid_total"}

        total = sum(item["subtotal"] for item in items)

        discount = 0
        applied_promo = None

        if promo_code:
            promo_info = await PromoCodeService.validate(shop_id, promo_code, total)

            if promo_info:
                discount = promo_info["discount_amount"]
                applied_promo = promo_info["code"]

        final_total = total - discount
        if final_total <= 0:
            return {"error": "invalid_total"}

        async with async_session() as session:
            # A shop-row lock serializes order creation and makes the unpaid-order
            # limits effective under concurrent/distributed requests.
            shop = (
                await session.execute(
                    select(Shop).where(Shop.id == shop_id).with_for_update()
                )
            ).scalar_one_or_none()
            if shop is None:
                return {"error": "shop_not_found"}

            locked_cart = list(
                (
                    await session.execute(
                        select(CartItem)
                        .where(
                            CartItem.shop_id == shop_id,
                            CartItem.telegram_user_id == telegram_user_id,
                        )
                        .order_by(CartItem.id)
                        .with_for_update()
                    )
                ).scalars().all()
            )
            expected = {
                (item["product_id"], item["variant_id"]): item["quantity"]
                for item in items
            }
            actual = {
                (item.product_id, item.variant_id): item.quantity
                for item in locked_cart
            }
            if not locked_cart or actual != expected:
                return {"error": "cart_changed"}

            now = datetime.now()
            active_reservation = (
                Order.payment_confirmed_at.is_(None),
                Order.stock_released_at.is_(None),
                Order.stock_reserved_until > now,
                Order.status.in_([OrderStatus.NEW, OrderStatus.CONFIRMED]),
            )
            user_unpaid = (
                await session.execute(
                    select(func.count()).select_from(Order).where(
                        Order.shop_id == shop_id,
                        Order.telegram_user_id == telegram_user_id,
                        *active_reservation,
                    )
                )
            ).scalar_one()
            if user_unpaid >= OrderService.MAX_ACTIVE_UNPAID_PER_USER:
                return {"error": "too_many_unpaid_orders"}

            shop_unpaid = (
                await session.execute(
                    select(func.count()).select_from(Order).where(
                        Order.shop_id == shop_id,
                        *active_reservation,
                    )
                )
            ).scalar_one()
            if shop_unpaid >= OrderService.MAX_ACTIVE_UNPAID_PER_SHOP:
                return {"error": "shop_order_limit"}

            out_of_stock: list[dict] = []

            for item in items:
                variant_id = item.get("variant_id")
                if variant_id:
                    result = await session.execute(
                        update(ProductVariant)
                        .where(
                            ProductVariant.id == variant_id,
                            ProductVariant.shop_id == shop_id,
                            ProductVariant.product_id == item["product_id"],
                            ProductVariant.stock >= item["quantity"],
                        )
                        .values(stock=ProductVariant.stock - item["quantity"])
                    )

                    if result.rowcount == 0:
                        variant = await session.get(ProductVariant, variant_id)
                        out_of_stock.append({
                            "product_name": item["product_name"],
                            "volume": item["volume"],
                            "requested": item["quantity"],
                            "available": variant.stock if variant else 0,
                        })

            if out_of_stock:
                await session.rollback()
                return {"error": "out_of_stock", "items": out_of_stock}

            if applied_promo:
                promo_ok = await PromoCodeService.try_increment_usage(
                    session, shop_id, applied_promo
                )
                if not promo_ok:
                    discount = 0
                    final_total = total
                    applied_promo = None

            order = Order(
                shop_id=shop_id,
                telegram_user_id=telegram_user_id,
                status=OrderStatus.NEW,
                full_name=full_name,
                phone=phone,
                address=address,
                comment=comment,
                total_amount=final_total,
                promo_code=applied_promo,
                discount_amount=discount,
                payment_method=payment_method,
                stock_reserved_until=now + timedelta(
                    minutes=OrderService.RESERVATION_MINUTES
                ),
            )

            order.items = [
                OrderItem(
                    shop_id=shop_id,
                    product_name=item["product_name"],
                    product_id=item["product_id"],
                    variant_id=item.get("variant_id"),
                    variant_volume=item["volume"],
                    price=item["price"],
                    quantity=item["quantity"],
                    source_ref_id=item.get("source_ref_id"),
                    source_post_id=item.get("source_post_id"),
                )
                for item in items
            ]

            session.add(order)
            await session.execute(
                delete(CartItem).where(
                    CartItem.shop_id == shop_id,
                    CartItem.telegram_user_id == telegram_user_id,
                )
            )
            await session.commit()
            await session.refresh(order)

            order_id = order.id

        for item in items:
            if item.get("discount_percent", 0) > 0:
                await OfferService.mark_used(
                    shop_id, telegram_user_id, item["product_id"], item["variant_id"]
                )

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
    async def get_order_owner(shop_id: int, order_id: int) -> int | None:
        """Возвращает telegram_user_id владельца заказа."""
        async with async_session() as session:
            result = await session.execute(
                select(Order.telegram_user_id).where(
                    Order.shop_id == shop_id,
                    Order.id == order_id,
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def has_purchased(shop_id: int, telegram_user_id: int, product_id: int) -> bool:
        """Проверяет, покупал ли пользователь данный товар (заказ не отменён)."""
        async with async_session() as session:
            result = await session.execute(
                select(
                    exists()
                    .where(
                        OrderItem.product_id == product_id,
                        OrderItem.order_id == Order.id,
                        Order.shop_id == shop_id,
                        Order.telegram_user_id == telegram_user_id,
                        Order.status != OrderStatus.CANCELLED,
                    )
                )
            )
            return bool(result.scalar())

    @staticmethod
    async def get_user_orders(shop_id: int, telegram_user_id: int, limit: int = 10) -> list[dict]:
        """Последние заказы пользователя (краткая информация)."""
        async with async_session() as session:
            result = await session.execute(
                select(Order)
                .where(
                    Order.shop_id == shop_id,
                    Order.telegram_user_id == telegram_user_id,
                )
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
        shop_id: int,
        telegram_user_id: int,
        order_id: int,
    ) -> dict | None:
        """Детальная информация о заказе пользователя."""
        async with async_session() as session:
            result = await session.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(
                    Order.shop_id == shop_id,
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

    @staticmethod
    async def auto_cancel_stale_orders(
        days: int | None = None,
        minutes: int = RESERVATION_MINUTES,
    ) -> int:
        """Отменяет заказы, которые не сменили статус за указанное число дней.

        Проверяет status_updated_at (или created_at, если поле пустое —
        старые заказы). Не трогает финальные статусы (done, cancelled, shipped).
        Возвращает количество отменённых заказов.
        """
        now = datetime.now()
        cutoff = now - (timedelta(days=days) if days is not None else timedelta(minutes=minutes))

        async with async_session() as session:
            result = await session.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(
                    Order.status.in_([OrderStatus.NEW, OrderStatus.CONFIRMED]),
                    Order.payment_confirmed_at.is_(None),
                    Order.stock_released_at.is_(None),
                    or_(
                        Order.stock_reserved_until < now,
                        Order.stock_reserved_until.is_(None),
                    ),
                    or_(
                        Order.status_updated_at.is_(None),
                        Order.status_updated_at < cutoff,
                    ),
                    Order.created_at < cutoff,
                )
            )
            stale = result.scalars().all()

            for order in stale:
                order.status = OrderStatus.CANCELLED
                order.status_updated_at = now
                order.stock_released_at = now

                for item in order.items:
                    if item.variant_id:
                        await session.execute(
                            update(ProductVariant)
                            .where(ProductVariant.id == item.variant_id)
                            .values(stock=ProductVariant.stock + item.quantity)
                        )

            if stale:
                await session.commit()

            return len(stale)
