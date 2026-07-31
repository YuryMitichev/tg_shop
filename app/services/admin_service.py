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
    async def get_categories() -> list[dict]:
        async with async_session() as session:
            result = await session.execute(select(Category).order_by(Category.id))
            return [_category_to_dict(c) for c in result.scalars().all()]

    @staticmethod
    async def create_category(name: str, emoji: str | None = None) -> int:
        async with async_session() as session:
            category = Category(name=name, emoji=emoji or None)
            session.add(category)
            await session.commit()
            await session.refresh(category)
            return category.id

    @staticmethod
    async def rename_category(category_id: int, name: str) -> None:
        async with async_session() as session:
            category = await session.get(Category, category_id)

            if category:
                category.name = name
                await session.commit()

    @staticmethod
    async def update_category_emoji(category_id: int, emoji: str | None) -> None:
        async with async_session() as session:
            category = await session.get(Category, category_id)

            if category:
                category.emoji = emoji or None
                await session.commit()

    @staticmethod
    async def count_products_in_category(category_id: int) -> int:
        async with async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(Product)
                .where(Product.category_id == category_id)
            )
            return result.scalar() or 0

    @staticmethod
    async def delete_category(category_id: int) -> bool:
        """
        Удаляет категорию.
        Возвращает False, если в категории есть товары.
        """
        count = await AdminService.count_products_in_category(category_id)

        if count > 0:
            return False

        async with async_session() as session:
            category = await session.get(Category, category_id)

            if category:
                await session.delete(category)
                await session.commit()

        return True

    # ==========================
    # Товары
    # ==========================

    @staticmethod
    async def get_products(category_id: int) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Product)
                .options(
                    selectinload(Product.variants),
                    selectinload(Product.photos),
                )
                .where(Product.category_id == category_id)
                .order_by(Product.id)
            )
            return [_product_to_dict(p) for p in result.scalars().all()]

    @staticmethod
    async def get_product(product_id: int) -> dict | None:
        async with async_session() as session:
            result = await session.execute(
                select(Product)
                .options(
                    selectinload(Product.variants),
                    selectinload(Product.photos),
                )
                .where(Product.id == product_id)
            )
            product = result.scalar_one_or_none()
            return _product_to_dict(product) if product else None

    @staticmethod
    async def create_product(
        category_id: int,
        name: str,
        description: str,
        variants: list[dict],
        photos: list[str] | None = None,
    ) -> int:
        async with async_session() as session:
            product = Product(
                category_id=category_id,
                name=name,
                description=description,
                is_active=True,
            )

            product.variants = [
                ProductVariant(
                    volume=variant["volume"],
                    price=variant["price"],
                    burn=variant.get("burn"),
                )
                for variant in variants
            ]

            if photos:
                product.photos = [
                    ProductPhoto(file_id=file_id, position=i)
                    for i, file_id in enumerate(photos)
                ]

            session.add(product)
            await session.commit()
            await session.refresh(product)

            return product.id

    @staticmethod
    async def delete_product(product_id: int) -> None:
        async with async_session() as session:
            product = await session.get(Product, product_id)

            if product:
                await session.delete(product)
                await session.commit()

    @staticmethod
    async def toggle_active(product_id: int) -> bool | None:
        async with async_session() as session:
            product = await session.get(Product, product_id)

            if not product:
                return None

            product.is_active = not product.is_active
            await session.commit()

            return product.is_active

    @staticmethod
    async def update_product(
        product_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        async with async_session() as session:
            product = await session.get(Product, product_id)

            if not product:
                return

            if name is not None:
                product.name = name
            if description is not None:
                product.description = description

            await session.commit()

    @staticmethod
    async def add_photo(product_id: int, file_id: str) -> int | None:
        async with async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(ProductPhoto)
                .where(ProductPhoto.product_id == product_id)
            )
            position = result.scalar() or 0

            photo = ProductPhoto(
                product_id=product_id,
                file_id=file_id,
                position=position,
            )
            session.add(photo)
            await session.commit()
            await session.refresh(photo)

            return photo.id

    @staticmethod
    async def delete_photo(photo_id: int) -> None:
        async with async_session() as session:
            photo = await session.get(ProductPhoto, photo_id)

            if photo:
                await session.delete(photo)
                await session.commit()

    # ==========================
    # Заказы
    # ==========================

    @staticmethod
    async def get_orders(limit: int = 10) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Order).order_by(Order.id.desc()).limit(limit)
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
    async def get_order(order_id: int) -> dict | None:
        async with async_session() as session:
            result = await session.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(Order.id == order_id)
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
    async def set_order_status(order_id: int, status: str) -> None:
        async with async_session() as session:
            order = await session.get(Order, order_id)

            if order:
                order.status = status
                await session.commit()

    # ==========================
    # Статистика
    # ==========================

    @staticmethod
    async def get_stats() -> dict:
        """
        Сводная статистика по магазину.
        Выручка считается по заказам, не отменённым (status != 'cancelled').
        """
        async with async_session() as session:
            # Кол-во заказов по статусам
            result = await session.execute(
                select(Order.status, func.count())
                .group_by(Order.status)
            )
            status_counts = {row[0]: row[1] for row in result.all()}

            total_orders = sum(status_counts.values())
            new_orders = status_counts.get("new", 0)
            cancelled_orders = status_counts.get("cancelled", 0)

            # Выручка за всё время (исключая отменённые)
            revenue_result = await session.execute(
                select(func.coalesce(func.sum(Order.total_amount), 0))
                .where(Order.status != "cancelled")
            )
            total_revenue = revenue_result.scalar() or 0

            # Выручка за текущий месяц
            now = datetime.now()
            month_revenue_result = await session.execute(
                select(func.coalesce(func.sum(Order.total_amount), 0))
                .where(
                    Order.status != "cancelled",
                    extract("year", Order.created_at) == now.year,
                    extract("month", Order.created_at) == now.month,
                )
            )
            month_revenue = month_revenue_result.scalar() or 0

            # Топ-5 товаров по выручке
            top_result = await session.execute(
                select(
                    OrderItem.product_name,
                    func.sum(OrderItem.quantity).label("qty"),
                    func.sum(OrderItem.price * OrderItem.quantity).label("revenue"),
                )
                .join(Order, OrderItem.order_id == Order.id)
                .where(Order.status != "cancelled")
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
    async def get_all_products() -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Product)
                .options(
                    selectinload(Product.variants),
                    selectinload(Product.photos),
                    selectinload(Product.category),
                )
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
        status: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        async with async_session() as session:
            query = select(Order).order_by(Order.id.desc())

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
    async def get_order_detail(order_id: int) -> dict | None:
        async with async_session() as session:
            result = await session.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(Order.id == order_id)
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
    async def get_users() -> list[dict]:
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
                .where(Order.status != "cancelled")
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
    async def get_all_reviews() -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Review).order_by(Review.created_at.desc())
            )

            reviews = []
            for r in result.scalars().all():
                product_name = None
                if r.product_id:
                    product = await session.get(Product, r.product_id)
                    product_name = product.name if product else None

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
    async def delete_review(review_id: int) -> bool:
        async with async_session() as session:
            review = await session.get(Review, review_id)

            if review:
                await session.delete(review)
                await session.commit()
                return True

            return False

    # ==========================
    # Аналитика (графики)
    # ==========================

    @staticmethod
    async def get_revenue_chart(days: int = 30) -> list[dict]:
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
