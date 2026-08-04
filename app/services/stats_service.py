from datetime import datetime, timedelta

from sqlalchemy import select, func, extract

from app.core.enums import OrderStatus
from app.database.db import async_session
from app.models.category import Category
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.review import Review


class StatsService:
    """Статистика и аналитика по магазину."""

    # ==========================
    # Сводная статистика
    # ==========================

    @staticmethod
    async def get_stats(shop_id: int) -> dict:
        """
        Сводная статистика по магазину.
        Выручка считается по заказам, не отменённым (status != 'cancelled').
        """
        async with async_session() as session:
            result = await session.execute(
                select(Order.status, func.count())
                .where(Order.shop_id == shop_id)
                .group_by(Order.status)
            )
            status_counts = {row[0]: row[1] for row in result.all()}

            total_orders = sum(status_counts.values())
            new_orders = status_counts.get(OrderStatus.NEW, 0)
            cancelled_orders = status_counts.get(OrderStatus.CANCELLED, 0)

            revenue_result = await session.execute(
                select(func.coalesce(func.sum(Order.total_amount), 0))
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                )
            )
            total_revenue = revenue_result.scalar() or 0

            now = datetime.now()
            month_revenue_result = await session.execute(
                select(func.coalesce(func.sum(Order.total_amount), 0))
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                    extract("year", Order.created_at) == now.year,
                    extract("month", Order.created_at) == now.month,
                )
            )
            month_revenue = month_revenue_result.scalar() or 0

            top_result = await session.execute(
                select(
                    OrderItem.product_name,
                    func.sum(OrderItem.quantity).label("qty"),
                    func.sum(OrderItem.price * OrderItem.quantity).label("revenue"),
                )
                .join(Order, OrderItem.order_id == Order.id)
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                )
                .group_by(OrderItem.product_name)
                .order_by(func.sum(OrderItem.price * OrderItem.quantity).desc())
                .limit(5)
            )

            top_products = [
                {
                    "name": row[0],
                    "quantity": row[1],
                    "revenue": row[2],
                }
                for row in top_result.all()
            ]

            return {
                "total_orders": total_orders,
                "new_orders": new_orders,
                "cancelled_orders": cancelled_orders,
                "total_revenue": total_revenue,
                "month_revenue": month_revenue,
                "top_products": top_products,
            }

    # ==========================
    # График выручки
    # ==========================

    @staticmethod
    async def get_revenue_chart(shop_id: int, days: int = 30) -> list[dict]:
        async with async_session() as session:
            now = datetime.now()
            start = now - timedelta(days=days)

            result = await session.execute(
                select(
                    func.date(Order.created_at).label("date"),
                    func.sum(Order.total_amount).label("revenue"),
                    func.count(Order.id).label("orders"),
                )
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                    Order.created_at >= start,
                )
                .group_by(func.date(Order.created_at))
                .order_by(func.date(Order.created_at))
            )

            return [
                {
                    "date": str(row[0]),
                    "revenue": row[1] or 0,
                    "orders": row[2],
                }
                for row in result.all()
            ]

    # ==========================
    # Расширенная аналитика
    # ==========================

    @staticmethod
    async def get_analytics_overview(shop_id: int, days: int = 30) -> dict:
        now = datetime.now()
        cur_start = now - timedelta(days=days)
        prev_start = cur_start - timedelta(days=days)

        async with async_session() as session:
            cur_rev = await StatsService._period_revenue(session, shop_id, cur_start, now)
            prev_rev = await StatsService._period_revenue(session, shop_id, prev_start, cur_start)

            cur_orders = await StatsService._period_orders(session, shop_id, cur_start, now)
            prev_orders = await StatsService._period_orders(session, shop_id, prev_start, cur_start)

            cur_aov = cur_rev / cur_orders if cur_orders else 0
            prev_aov = prev_rev / prev_orders if prev_orders else 0

            cur_customers = await StatsService._period_unique_customers(session, shop_id, cur_start, now)
            prev_customers = await StatsService._period_unique_customers(session, shop_id, prev_start, cur_start)

            cur_repeat = await StatsService._period_repeat_customers(session, shop_id, cur_start, now)

            cur_items = await StatsService._period_total_items(session, shop_id, cur_start, now)
            avg_items = cur_items / cur_orders if cur_orders else 0

            completed_result = await session.execute(
                select(func.count())
                .select_from(Order)
                .where(
                    Order.shop_id == shop_id,
                    Order.status == OrderStatus.DONE,
                    Order.created_at >= cur_start,
                )
            )
            completed = completed_result.scalar() or 0

            completion_rate = completed / cur_orders * 100 if cur_orders else 0

            return {
                "revenue": cur_rev,
                "revenue_growth": StatsService._growth_pct(cur_rev, prev_rev),
                "orders": cur_orders,
                "orders_growth": StatsService._growth_pct(cur_orders, prev_orders),
                "avg_order_value": cur_aov,
                "aov_growth": StatsService._growth_pct(cur_aov, prev_aov),
                "unique_customers": cur_customers,
                "customers_growth": StatsService._growth_pct(cur_customers, prev_customers),
                "completed_orders": completed,
                "completion_rate": round(completion_rate, 1),
                "repeat_customers": cur_repeat,
                "repeat_rate": round(cur_repeat / cur_customers * 100, 1) if cur_customers else 0,
                "avg_items_per_order": round(avg_items, 1),
            }

    @staticmethod
    async def _period_revenue(session, shop_id: int, start, end) -> int:
        result = await session.execute(
            select(func.coalesce(func.sum(Order.total_amount), 0))
            .where(
                Order.shop_id == shop_id,
                Order.status != OrderStatus.CANCELLED,
                Order.created_at >= start,
                Order.created_at < end,
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def _period_orders(session, shop_id: int, start, end) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(Order)
            .where(
                Order.shop_id == shop_id,
                Order.status != OrderStatus.CANCELLED,
                Order.created_at >= start,
                Order.created_at < end,
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def _period_unique_customers(session, shop_id: int, start, end) -> int:
        result = await session.execute(
            select(func.count(func.distinct(Order.telegram_user_id)))
            .where(
                Order.shop_id == shop_id,
                Order.status != OrderStatus.CANCELLED,
                Order.created_at >= start,
                Order.created_at < end,
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def _period_repeat_customers(session, shop_id: int, start, end) -> int:
        result = await session.execute(
            select(Order.telegram_user_id, func.count(Order.id).label("cnt"))
            .where(
                Order.shop_id == shop_id,
                Order.status != OrderStatus.CANCELLED,
                Order.created_at >= start,
                Order.created_at < end,
            )
            .group_by(Order.telegram_user_id)
        )
        return sum(1 for row in result.all() if row[1] > 1)

    @staticmethod
    async def _period_total_items(session, shop_id: int, start, end) -> int:
        result = await session.execute(
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.shop_id == shop_id,
                Order.status != OrderStatus.CANCELLED,
                Order.created_at >= start,
                Order.created_at < end,
            )
        )
        return result.scalar() or 0

    @staticmethod
    def _growth_pct(current: float | int, previous: float | int) -> float:
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round((current - previous) / previous * 100, 1)

    # ==========================
    # Разрезы аналитики
    # ==========================

    @staticmethod
    async def get_category_breakdown(shop_id: int, days: int = 30) -> list[dict]:
        now = datetime.now()
        start = now - timedelta(days=days)

        async with async_session() as session:
            result = await session.execute(
                select(
                    Category.id,
                    Category.name,
                    Category.emoji,
                    func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0).label("revenue"),
                    func.coalesce(func.sum(OrderItem.quantity), 0).label("quantity"),
                )
                .join(Product, Product.category_id == Category.id)
                .join(OrderItem, OrderItem.product_id == Product.id, isouter=True)
                .join(Order, OrderItem.order_id == Order.id, isouter=True)
                .where(
                    Category.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                    Order.created_at >= start,
                )
                .group_by(Category.id, Category.name, Category.emoji)
                .order_by(func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0).desc())
            )

            return [
                {
                    "id": row[0],
                    "name": row[1],
                    "emoji": row[2],
                    "revenue": row[3],
                    "quantity": row[4],
                }
                for row in result.all()
            ]

    @staticmethod
    async def get_product_stats(shop_id: int, days: int = 30, limit: int = 10) -> list[dict]:
        now = datetime.now()
        start = now - timedelta(days=days)

        async with async_session() as session:
            result = await session.execute(
                select(
                    OrderItem.product_name,
                    func.sum(OrderItem.quantity).label("qty"),
                    func.sum(OrderItem.price * OrderItem.quantity).label("revenue"),
                )
                .join(Order, OrderItem.order_id == Order.id)
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                    Order.created_at >= start,
                )
                .group_by(OrderItem.product_name)
                .order_by(func.sum(OrderItem.quantity).desc())
                .limit(limit)
            )

            return [
                {
                    "name": row[0],
                    "quantity": row[1],
                    "revenue": row[2],
                }
                for row in result.all()
            ]

    @staticmethod
    async def get_customer_stats(shop_id: int, days: int = 30) -> dict:
        now = datetime.now()
        start = now - timedelta(days=days)

        async with async_session() as session:
            first_order_result = await session.execute(
                select(Order.telegram_user_id, func.min(Order.created_at).label("first"))
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                )
                .group_by(Order.telegram_user_id)
            )
            all_customers = first_order_result.all()

            new_customers = sum(1 for row in all_customers if row[1] and row[1] >= start.replace(tzinfo=None))
            returning_customers = len(all_customers) - new_customers

            total_rev_result = await session.execute(
                select(func.coalesce(func.sum(Order.total_amount), 0))
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                )
            )
            total_revenue = total_rev_result.scalar() or 0

            ltv = total_revenue / len(all_customers) if all_customers else 0

            top_customers_result = await session.execute(
                select(
                    Order.full_name,
                    func.count(Order.id).label("orders"),
                    func.sum(Order.total_amount).label("spent"),
                )
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                )
                .group_by(Order.full_name)
                .order_by(func.sum(Order.total_amount).desc())
                .limit(5)
            )

            top_customers = [
                {"name": row[0], "orders": row[1], "spent": row[2] or 0}
                for row in top_customers_result.all()
            ]

            return {
                "new_customers": new_customers,
                "returning_customers": returning_customers,
                "total_customers": len(all_customers),
                "ltv": round(ltv),
                "top_customers": top_customers,
            }

    @staticmethod
    async def get_promo_stats(shop_id: int, days: int = 30) -> dict:
        now = datetime.now()
        start = now - timedelta(days=days)

        async with async_session() as session:
            total_discount_result = await session.execute(
                select(func.coalesce(func.sum(Order.discount_amount), 0))
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                    Order.created_at >= start,
                    Order.discount_amount > 0,
                )
            )
            total_discount = total_discount_result.scalar() or 0

            with_promo_result = await session.execute(
                select(func.count())
                .select_from(Order)
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                    Order.created_at >= start,
                    Order.promo_code.isnot(None),
                )
            )
            orders_with_promo = with_promo_result.scalar() or 0

            without_promo_result = await session.execute(
                select(func.count())
                .select_from(Order)
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                    Order.created_at >= start,
                    Order.promo_code.is_(None),
                )
            )
            orders_without_promo = without_promo_result.scalar() or 0

            top_promos_result = await session.execute(
                select(
                    Order.promo_code,
                    func.count(Order.id).label("uses"),
                    func.sum(Order.discount_amount).label("discount"),
                )
                .where(
                    Order.shop_id == shop_id,
                    Order.status != OrderStatus.CANCELLED,
                    Order.created_at >= start,
                    Order.promo_code.isnot(None),
                )
                .group_by(Order.promo_code)
                .order_by(func.count(Order.id).desc())
                .limit(5)
            )

            top_promos = [
                {"code": row[0], "uses": row[1], "discount": row[2] or 0}
                for row in top_promos_result.all()
            ]

            return {
                "total_discount": total_discount,
                "orders_with_promo": orders_with_promo,
                "orders_without_promo": orders_without_promo,
                "top_promos": top_promos,
            }

    @staticmethod
    async def get_review_stats(shop_id: int) -> dict:
        async with async_session() as session:
            avg_result = await session.execute(
                select(func.coalesce(func.avg(Review.rating), 0))
                .where(Review.shop_id == shop_id)
            )
            avg_rating = round(avg_result.scalar() or 0, 1)

            dist_result = await session.execute(
                select(Review.rating, func.count())
                .where(Review.shop_id == shop_id)
                .group_by(Review.rating)
            )
            distribution = {str(r[0]): r[1] for r in dist_result.all()}

            total_result = await session.execute(
                select(func.count())
                .select_from(Review)
                .where(Review.shop_id == shop_id)
            )
            total = total_result.scalar() or 0

            return {
                "avg_rating": avg_rating,
                "total_reviews": total,
                "distribution": {str(i): distribution.get(str(i), 0) for i in range(1, 6)},
            }
