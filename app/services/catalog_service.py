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
                "burn": variant.burn,
                "photo": variant.photo,
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
    async def get_categories() -> list[dict]:
        """Получить список категорий."""
        async with async_session() as session:
            result = await session.execute(
                select(Category).order_by(Category.id)
            )
            return [_category_to_dict(c) for c in result.scalars().all()]

    @staticmethod
    async def get_category(category_id: int) -> dict | None:
        """Получить категорию по ID."""
        async with async_session() as session:
            category = await session.get(Category, category_id)
            return _category_to_dict(category) if category else None

    @staticmethod
    async def get_products(category_id: int) -> list[dict]:
        """Получить товары категории (только видимые покупателям)."""
        async with async_session() as session:
            result = await session.execute(
                select(Product)
                .options(
                    selectinload(Product.variants),
                    selectinload(Product.photos),
                )
                .where(
                    Product.category_id == category_id,
                    Product.is_active == True,  # noqa: E712
                )
                .order_by(Product.id)
            )
            return [_product_to_dict(p) for p in result.scalars().all()]

    @staticmethod
    async def get_product(product_id: int) -> dict | None:
        """Получить товар по ID (только если виден покупателям)."""
        async with async_session() as session:
            result = await session.execute(
                select(Product)
                .options(
                    selectinload(Product.variants),
                    selectinload(Product.photos),
                )
                .where(
                    Product.id == product_id,
                    Product.is_active == True,  # noqa: E712
                )
            )
            product = result.scalar_one_or_none()
            return _product_to_dict(product) if product else None

    @staticmethod
    async def get_first_product(category_id: int) -> dict | None:
        """Первый товар категории."""
        products = await CatalogService.get_products(category_id)
        return products[0] if products else None

    @staticmethod
    async def get_next_product(category_id: int, current_product_id: int) -> dict | None:
        """Следующий товар (циклически)."""
        products = await CatalogService.get_products(category_id)

        if not products:
            return None

        for index, product in enumerate(products):
            if product["id"] == current_product_id:
                return products[(index + 1) % len(products)]

        return products[0]

    @staticmethod
    async def get_previous_product(category_id: int, current_product_id: int) -> dict | None:
        """Предыдущий товар (циклически)."""
        products = await CatalogService.get_products(category_id)

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
    async def get_product_position(category_id: int, product_id: int) -> tuple[int, int]:
        """
        Возвращает:
        (текущая_позиция, всего_товаров)
        """
        products = await CatalogService.get_products(category_id)

        total = len(products)

        for index, product in enumerate(products):
            if product["id"] == product_id:
                return index + 1, total

        return 1, total
