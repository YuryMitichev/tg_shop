from sqlalchemy import func, select

from app.database.db import async_session
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant


async def seed_if_empty() -> None:
    """
    Заполняет БД стартовым каталогом при первом запуске.

    Если категории уже есть — ничего не делает (безопасно
    вызывать при каждом старте бота).
    """
    async with async_session() as session:
        count = await session.scalar(select(func.count()).select_from(Category))

        if count:
            return

        session.add_all([
            Category(id=1, name="Ароматические свечи", emoji="🕯"),
            Category(id=2, name="Диффузоры", emoji="🏠"),
            Category(id=3, name="Подарочные наборы", emoji="🎁"),
        ])

        session.add_all([
            Product(
                id=1,
                category_id=1,
                name="Кашемир и амбровая кожа",
                description="Теплый древесный аромат.",
                variants=[
                    ProductVariant(id=1, volume="75 г", price=450, burn="10 часов", stock=10),
                    ProductVariant(id=2, volume="200 г", price=990, burn="45 часов", stock=10),
                    ProductVariant(id=3, volume="400 г", price=1650, burn="90 часов", stock=5),
                ],
            ),
            Product(
                id=2,
                category_id=1,
                name="Белый чай",
                description="Легкий свежий аромат.",
                variants=[
                    ProductVariant(id=4, volume="75 г", price=450, burn="10 часов", stock=10),
                    ProductVariant(id=5, volume="200 г", price=990, burn="45 часов", stock=10),
                ],
            ),
            Product(
                id=3,
                category_id=2,
                name="Кашемир и амбровая кожа",
                description="Диффузор для дома.",
                variants=[
                    ProductVariant(id=6, volume="100 мл", price=1290, stock=5),
                ],
            ),
        ])

        await session.commit()
