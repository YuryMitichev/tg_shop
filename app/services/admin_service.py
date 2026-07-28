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


def _category_to_dict(category: Category) -> dict:
    return {
        "id": category.id,
        "name": category.name,
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
    async def create_category(name: str) -> int:
        async with async_session() as session:
            category = Category(name=name)
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
