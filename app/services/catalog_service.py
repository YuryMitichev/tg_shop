from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.db import async_session
from app.models.category import Category
from app.models.product import Product
from app.models.product_photo import ProductPhoto


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
        "variants": [
            {
                "id": variant.id,
                "volume": variant.volume,
                "price": variant.price,
                "photo": variant.photo,
                "stock": variant.stock,
                "attributes": variant.attributes or {},
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


class CatalogService:
    """
    Работа с каталогом.

    Методы, которые ходят в БД, — async (get_categories, get_category,
    get_products, get_product, get_first_product, get_next_product,
    get_previous_product, get_product_position).

    get_variant / get_first_variant остаются синхронными: они работают
    с уже загруженным словарём товара, а не с БД напрямую.
    """

    @staticmethod
    async def get_categories(shop_id: int) -> list[dict]:
        """Получить список категорий."""
        async with async_session() as session:
            result = await session.execute(
                select(Category)
                .where(Category.shop_id == shop_id)
                .order_by(Category.id)
            )
            return [_category_to_dict(c) for c in result.scalars().all()]

    @staticmethod
    async def get_category(shop_id: int, category_id: int) -> dict | None:
        """Получить категорию по ID."""
        async with async_session() as session:
            result = await session.execute(
                select(Category)
                .where(
                    Category.shop_id == shop_id,
                    Category.id == category_id,
                )
            )
            category = result.scalar_one_or_none()
            return _category_to_dict(category) if category else None

    @staticmethod
    async def get_products(shop_id: int, category_id: int) -> list[dict]:
        """Получить товары категории (только видимые покупателям)."""
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
                    Product.is_active == True,  # noqa: E712
                )
                .order_by(Product.id)
            )
            return [_product_to_dict(p) for p in result.scalars().all()]

    @staticmethod
    async def get_product(shop_id: int, product_id: int) -> dict | None:
        """Получить товар по ID (только если виден покупателям)."""
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
                    Product.is_active == True,  # noqa: E712
                )
            )
            product = result.scalar_one_or_none()
            return _product_to_dict(product) if product else None

    @staticmethod
    async def get_products_by_ids(shop_id: int, product_ids: list[int]) -> list[dict]:
        """Получить видимые товары магазина по списку ID."""
        if not product_ids:
            return []

        async with async_session() as session:
            result = await session.execute(
                select(Product)
                .options(
                    selectinload(Product.variants),
                    selectinload(Product.photos),
                )
                .where(
                    Product.shop_id == shop_id,
                    Product.id.in_(product_ids),
                    Product.is_active == True,  # noqa: E712
                )
            )
            products = {
                product.id: _product_to_dict(product)
                for product in result.scalars().all()
            }
            return [
                products[product_id]
                for product_id in product_ids
                if product_id in products
            ]

    @staticmethod
    async def get_first_product(shop_id: int, category_id: int) -> dict | None:
        """Первый товар категории."""
        products = await CatalogService.get_products(shop_id, category_id)
        return products[0] if products else None

    @staticmethod
    async def get_next_product(shop_id: int, category_id: int, current_product_id: int) -> dict | None:
        """Следующий товар (циклически)."""
        products = await CatalogService.get_products(shop_id, category_id)

        if not products:
            return None

        for index, product in enumerate(products):
            if product["id"] == current_product_id:
                return products[(index + 1) % len(products)]

        return products[0]

    @staticmethod
    async def get_previous_product(shop_id: int, category_id: int, current_product_id: int) -> dict | None:
        """Предыдущий товар (циклически)."""
        products = await CatalogService.get_products(shop_id, category_id)

        if not products:
            return None

        for index, product in enumerate(products):
            if product["id"] == current_product_id:
                return products[(index - 1) % len(products)]

        return products[0]

    @staticmethod
    def get_variant(product: dict, variant_id: int) -> dict | None:
        """Получить вариант товара."""
        return next(
            (
                variant
                for variant in product["variants"]
                if variant["id"] == variant_id
            ),
            None,
        )

    @staticmethod
    def get_first_variant(product: dict) -> dict:
        """Первый вариант товара."""
        return product["variants"][0]

    @staticmethod
    async def get_product_position(shop_id: int, category_id: int, product_id: int) -> tuple[int, int]:
        """
        Возвращает:
        (текущая_позиция, всего_товаров)
        """
        products = await CatalogService.get_products(shop_id, category_id)

        total = len(products)

        for index, product in enumerate(products):
            if product["id"] == product_id:
                return index + 1, total

        return 1, total
