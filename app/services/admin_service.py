from datetime import datetime

from sqlalchemy import select, func, extract
from sqlalchemy.orm import selectinload

from app.database.db import async_session
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.product_photo import ProductPhoto
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.review import Review


def _category_to_dict(category: Category) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "emoji": category.emoji,
    }


def _product_to_dict(product: Product) -> dict:
    return {
        "id": product.id,
        "category_id": product.category_id,
        "name": product.name,
        "description": product.description,
        "is_active": product.is_active,
        "variants": [
            {
                "id": variant.id,
                "volume": variant.volume,
                "price": variant.price,
                "burn": variant.burn,
                "stock": variant.stock,
            }
            for variant in product.variants
        ],
        "photos": [
            {
                "id": photo.id,
                "file_id": photo.file_id,
                "position": photo.position,
            }
            for photo in product.photos
        ],
    }


class AdminService:
    """
    В отличие от CatalogService, видит вообще все товары —
    включая скрытые (is_active=False). Только для админки.
    """

    # ==========================
    # Категории
    # ==========================

    @staticmethod
    async def get_categories(shop_id: int) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Category)
                .where(Category.shop_id == shop_id)
                .order_by(Category.id)
            )
            return [_category_to_dict(c) for c in result.scalars().all()]

    @staticmethod
    async def create_category(shop_id: int, name: str, emoji: str | None = None) -> int:
        async with async_session() as session:
            category = Category(shop_id=shop_id, name=name, emoji=emoji or None)
            session.add(category)
            await session.commit()
            await session.refresh(category)
            return category.id

    @staticmethod
    async def rename_category(shop_id: int, category_id: int, name: str) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(Category).where(
                    Category.shop_id == shop_id,
                    Category.id == category_id,
                )
            )
            category = result.scalar_one_or_none()
            if category:
                category.name = name
                await session.commit()

    @staticmethod
    async def update_category_emoji(shop_id: int, category_id: int, emoji: str | None) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(Category).where(
                    Category.shop_id == shop_id,
                    Category.id == category_id,
                )
            )
            category = result.scalar_one_or_none()
            if category:
                category.emoji = emoji or None
                await session.commit()

    @staticmethod
    async def count_products_in_category(shop_id: int, category_id: int) -> int:
        async with async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(Product)
                .where(
                    Product.shop_id == shop_id,
                    Product.category_id == category_id,
                )
            )
            return result.scalar() or 0

    @staticmethod
    async def delete_category(shop_id: int, category_id: int) -> bool:
        """
        Удаляет категорию.
        Возвращает False, если в категории есть товары.
        """
        count = await AdminService.count_products_in_category(shop_id, category_id)

        if count > 0:
            return False

        async with async_session() as session:
            result = await session.execute(
                select(Category).where(
                    Category.shop_id == shop_id,
                    Category.id == category_id,
                )
            )
            category = result.scalar_one_or_none()

            if category:
                await session.delete(category)
                await session.commit()

        return True

    # ==========================
    # Товары
    # ==========================

    @staticmethod
    async def get_products(shop_id: int, category_id: int) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Product)
                .options(
                    selectinload(Product.variants),
                    selectinload(Product.photos),
                )
                .where(
                    Product.shop_id == shop_id,
                    Product.category_id == category_id,
                )
                .order_by(Product.id)
            )
            return [_product_to_dict(p) for p in result.scalars().all()]

    @staticmethod
    async def get_product(shop_id: int, product_id: int) -> dict | None:
        async with async_session() as session:
            result = await session.execute(
                select(Product)
                .options(
                    selectinload(Product.variants),
                    selectinload(Product.photos),
                )
                .where(
                    Product.shop_id == shop_id,
                    Product.id == product_id,
                )
            )
            product = result.scalar_one_or_none()
            return _product_to_dict(product) if product else None

    @staticmethod
    async def create_product(
        shop_id: int,
        category_id: int,
        name: str,
        description: str,
        variants: list[dict],
        photos: list[str] | None = None,
    ) -> int:
        async with async_session() as session:
            product = Product(
                shop_id=shop_id,
                category_id=category_id,
                name=name,
                description=description,
                is_active=True,
            )

            product.variants = [
                ProductVariant(
                    shop_id=shop_id,
                    volume=variant["volume"],
                    price=variant["price"],
                    burn=variant.get("burn"),
                    stock=variant.get("stock", 0),
                )
                for variant in variants
            ]

            if photos:
                product.photos = [
                    ProductPhoto(shop_id=shop_id, file_id=file_id, position=i)
                    for i, file_id in enumerate(photos)
                ]

            session.add(product)
            await session.commit()
            await session.refresh(product)

            return product.id

    @staticmethod
    async def delete_product(shop_id: int, product_id: int) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(Product).where(
                    Product.shop_id == shop_id,
                    Product.id == product_id,
                )
            )
            product = result.scalar_one_or_none()
            if product:
                await session.delete(product)
                await session.commit()

    @staticmethod
    async def toggle_active(shop_id: int, product_id: int) -> bool | None:
        async with async_session() as session:
            result = await session.execute(
                select(Product).where(
                    Product.shop_id == shop_id,
                    Product.id == product_id,
                )
            )
            product = result.scalar_one_or_none()

            if not product:
                return None

            product.is_active = not product.is_active
            await session.commit()

            return product.is_active

    @staticmethod
    async def update_product(
        shop_id: int,
        product_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(Product).where(
                    Product.shop_id == shop_id,
                    Product.id == product_id,
                )
            )
            product = result.scalar_one_or_none()

            if not product:
                return

            if name is not None:
                product.name = name
            if description is not None:
                product.description = description

            await session.commit()

    @staticmethod
    async def update_variant_stock(shop_id: int, variant_id: int, stock: int) -> bool:
        async with async_session() as session:
            result = await session.execute(
                select(ProductVariant).where(
                    ProductVariant.shop_id == shop_id,
                    ProductVariant.id == variant_id,
                )
            )
            variant = result.scalar_one_or_none()

            if not variant:
                return False

            variant.stock = max(0, stock)
            await session.commit()
            return True

    @staticmethod
    async def add_photo(shop_id: int, product_id: int, file_id: str) -> int | None:
        async with async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(ProductPhoto)
                .where(
                    ProductPhoto.shop_id == shop_id,
                    ProductPhoto.product_id == product_id,
                )
            )
            position = result.scalar() or 0

            photo = ProductPhoto(
                shop_id=shop_id,
                product_id=product_id,
                file_id=file_id,
                position=position,
            )
            session.add(photo)
            await session.commit()
            await session.refresh(photo)

            return photo.id

    @staticmethod
    async def delete_photo(shop_id: int, photo_id: int) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(ProductPhoto).where(
                    ProductPhoto.shop_id == shop_id,
                    ProductPhoto.id == photo_id,
                )
            )
            photo = result.scalar_one_or_none()
            if photo:
                await session.delete(photo)
                await session.commit()

    # ==========================
    # Заказы
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

            if old_status != "cancelled" and status == "cancelled":
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

            await session.commit()

    # ==========================
    # Статистика
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
            new_orders = status_counts.get("new", 0)
            cancelled_orders = status_counts.get("cancelled", 0)

            revenue_result = await session.execute(
                select(func.coalesce(func.sum(Order.total_amount), 0))
                .where(
                    Order.shop_id == shop_id,
                    Order.status != "cancelled",
                )
            )
            total_revenue = revenue_result.scalar() or 0

            now = datetime.now()
            month_revenue_result = await session.execute(
                select(func.coalesce(func.sum(Order.total_amount), 0))
                .where(
                    Order.shop_id == shop_id,
                    Order.status != "cancelled",
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
                    Order.status != "cancelled",
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
    # Все товары (вне категорий)
    # ==========================

    @staticmethod
    async def get_all_products(shop_id: int) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Product)
                .options(
                    selectinload(Product.variants),
                    selectinload(Product.photos),
                    selectinload(Product.category),
                )
                .where(Product.shop_id == shop_id)
                .order_by(Product.id.desc())
            )
            products = result.scalars().all()

            return [
                {
                    **_product_to_dict(p),
                    "category_name": p.category.name if p.category else None,
                }
                for p in products
            ]

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
                    Order.status != "cancelled",
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

    # ==========================
    # Отзывы (все)
    # ==========================

    @staticmethod
    async def get_all_reviews(shop_id: int) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Review)
                .where(Review.shop_id == shop_id)
                .order_by(Review.created_at.desc())
            )

            reviews = []
            for r in result.scalars().all():
                product_name = None
                if r.product_id:
                    prod_result = await session.execute(
                        select(Product.name).where(Product.id == r.product_id)
                    )
                    product_name = prod_result.scalar_one_or_none()

                reviews.append({
                    "id": r.id,
                    "product_id": r.product_id,
                    "product_name": product_name,
                    "telegram_user_id": r.telegram_user_id,
                    "rating": r.rating,
                    "text": r.text,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                })

            return reviews

    @staticmethod
    async def delete_review(shop_id: int, review_id: int) -> bool:
        async with async_session() as session:
            result = await session.execute(
                select(Review).where(
                    Review.shop_id == shop_id,
                    Review.id == review_id,
                )
            )
            review = result.scalar_one_or_none()

            if review:
                await session.delete(review)
                await session.commit()
                return True

            return False

    # ==========================
    # Аналитика (графики)
    # ==========================

    @staticmethod
    async def get_revenue_chart(shop_id: int, days: int = 30) -> list[dict]:
        from datetime import timedelta

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
                    Order.status != "cancelled",
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
        from datetime import timedelta

        now = datetime.now()
        cur_start = now - timedelta(days=days)
        prev_start = cur_start - timedelta(days=days)

        async with async_session() as session:
            cur_rev = await AdminService._period_revenue(session, shop_id, cur_start, now)
            prev_rev = await AdminService._period_revenue(session, shop_id, prev_start, cur_start)

            cur_orders = await AdminService._period_orders(session, shop_id, cur_start, now)
            prev_orders = await AdminService._period_orders(session, shop_id, prev_start, cur_start)

            cur_aov = cur_rev / cur_orders if cur_orders else 0
            prev_aov = prev_rev / prev_orders if prev_orders else 0

            cur_customers = await AdminService._period_unique_customers(session, shop_id, cur_start, now)
            prev_customers = await AdminService._period_unique_customers(session, shop_id, prev_start, cur_start)

            cur_repeat = await AdminService._period_repeat_customers(session, shop_id, cur_start, now)

            cur_items = await AdminService._period_total_items(session, shop_id, cur_start, now)
            avg_items = cur_items / cur_orders if cur_orders else 0

            completed_result = await session.execute(
                select(func.count())
                .select_from(Order)
                .where(
                    Order.shop_id == shop_id,
                    Order.status == "done",
                    Order.created_at >= cur_start,
                )
            )
            completed = completed_result.scalar() or 0

            completion_rate = completed / cur_orders * 100 if cur_orders else 0

            return {
                "revenue": cur_rev,
                "revenue_growth": AdminService._growth_pct(cur_rev, prev_rev),
                "orders": cur_orders,
                "orders_growth": AdminService._growth_pct(cur_orders, prev_orders),
                "avg_order_value": cur_aov,
                "aov_growth": AdminService._growth_pct(cur_aov, prev_aov),
                "unique_customers": cur_customers,
                "customers_growth": AdminService._growth_pct(cur_customers, prev_customers),
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
                Order.status != "cancelled",
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
                Order.status != "cancelled",
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
                Order.status != "cancelled",
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
                Order.status != "cancelled",
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
                Order.status != "cancelled",
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

    @staticmethod
    async def get_category_breakdown(shop_id: int, days: int = 30) -> list[dict]:
        from datetime import timedelta

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
                    Order.status != "cancelled",
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
        from datetime import timedelta

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
                    Order.status != "cancelled",
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
        from datetime import timedelta

        now = datetime.now()
        start = now - timedelta(days=days)

        async with async_session() as session:
            first_order_result = await session.execute(
                select(Order.telegram_user_id, func.min(Order.created_at).label("first"))
                .where(
                    Order.shop_id == shop_id,
                    Order.status != "cancelled",
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
                    Order.status != "cancelled",
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
                    Order.status != "cancelled",
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
        from datetime import timedelta

        now = datetime.now()
        start = now - timedelta(days=days)

        async with async_session() as session:
            total_discount_result = await session.execute(
                select(func.coalesce(func.sum(Order.discount_amount), 0))
                .where(
                    Order.shop_id == shop_id,
                    Order.status != "cancelled",
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
                    Order.status != "cancelled",
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
                    Order.status != "cancelled",
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
                    Order.status != "cancelled",
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
