from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.enums import OrderStatus
from app.database.db import async_session
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product_variant import ProductVariant
from app.services.sales_service import SalesService


class OrderAdminService:
    """Управление заказами и пользователями в админке."""

    # ==========================
    # Заказы (простые)
    # ==========================

    @staticmethod
    async def get_orders(shop_id: int, limit: int = 10) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Order)
                .where(Order.shop_id == shop_id)
                .order_by(Order.id.desc())
                .limit(limit)
            )

            return [
                {
                    "id": order.id,
                    "status": order.status,
                    "full_name": order.full_name,
                    "total_amount": order.total_amount,
                }
                for order in result.scalars().all()
            ]

    @staticmethod
    async def get_order(shop_id: int, order_id: int) -> dict | None:
        async with async_session() as session:
            result = await session.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(
                    Order.shop_id == shop_id,
                    Order.id == order_id,
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
                "total_amount": order.total_amount,
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
    async def set_order_status(shop_id: int, order_id: int, status: str) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(
                    Order.shop_id == shop_id,
                    Order.id == order_id,
                )
            )
            order = result.scalar_one_or_none()

            if not order:
                return

            old_status = order.status
            order.status = status
            order.status_updated_at = datetime.now()

            if status == OrderStatus.PAID:
                order.stock_reserved_until = None
                SalesService.confirm_order(
                    order,
                    source="manual",
                    reference=f"admin_status:{order_id}",
                    confirmed_at=order.status_updated_at,
                )

            if (
                old_status != OrderStatus.CANCELLED
                and status == OrderStatus.CANCELLED
                and order.stock_released_at is None
            ):
                for item in order.items:
                    if item.variant_id:
                        result_v = await session.execute(
                            select(ProductVariant).where(
                                ProductVariant.shop_id == shop_id,
                                ProductVariant.id == item.variant_id,
                            )
                        )
                        variant = result_v.scalar_one_or_none()
                        if variant:
                            variant.stock += item.quantity
                order.stock_released_at = order.status_updated_at

            await session.commit()
            SalesService.invalidate_analytics()

    # ==========================
    # Заказы (расширенные)
    # ==========================

    @staticmethod
    async def get_orders_filtered(
        shop_id: int,
        status: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        async with async_session() as session:
            query = (
                select(Order)
                .where(Order.shop_id == shop_id)
                .order_by(Order.id.desc())
            )

            if status:
                query = query.where(Order.status == status)

            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total = total_result.scalar() or 0

            result = await session.execute(
                query.offset((page - 1) * per_page).limit(per_page)
            )

            orders = []
            for order in result.scalars().all():
                orders.append({
                    "id": order.id,
                    "status": order.status,
                    "full_name": order.full_name,
                    "phone": order.phone,
                    "total_amount": order.total_amount,
                    "promo_code": order.promo_code,
                    "discount_amount": order.discount_amount,
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                    "telegram_user_id": order.telegram_user_id,
                })

            return {
                "orders": orders,
                "total": total,
                "page": page,
                "per_page": per_page,
            }

    @staticmethod
    async def get_order_detail(shop_id: int, order_id: int) -> dict | None:
        async with async_session() as session:
            result = await session.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(
                    Order.shop_id == shop_id,
                    Order.id == order_id,
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
                "promo_code": order.promo_code,
                "discount_amount": order.discount_amount,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "telegram_user_id": order.telegram_user_id,
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

    # ==========================
    # Пользователи
    # ==========================

    @staticmethod
    async def get_users(shop_id: int) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(
                    Order.telegram_user_id,
                    Order.full_name,
                    Order.phone,
                    func.count(Order.id).label("orders_count"),
                    func.sum(Order.total_amount).label("total_spent"),
                    func.max(Order.created_at).label("last_order"),
                )
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                )
                .group_by(Order.telegram_user_id, Order.full_name, Order.phone)
                .order_by(func.sum(Order.total_amount).desc())
            )

            return [
                {
                    "telegram_user_id": row[0],
                    "full_name": row[1],
                    "phone": row[2],
                    "orders_count": row[3],
                    "total_spent": row[4] or 0,
                    "last_order": row[5].isoformat() if row[5] else None,
                }
                for row in result.all()
            ]
