import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.database.db as db_module
import app.services.admin_service as admin_service
import app.services.admin_user_service as admin_user_service
import app.services.cart_service as cart_service
import app.services.catalog_service as catalog_service
import app.services.order_service as order_service
import app.services.review_service as review_service
import app.services.promo_service as promo_service
from app.database.db import Base
from app.models import (  # noqa: F401 — импорт регистрирует таблицы в metadata
    CartItem,
    Category,
    Order,
    OrderItem,
    Product,
    ProductPhoto,
    ProductVariant,
    Review,
    PromoCode,
    AdminUser,
)



TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_PATCH_TARGETS = [
    db_module,
    catalog_service,
    cart_service,
    order_service,
    admin_service,
    admin_user_service,
    review_service,
    promo_service,
]


@pytest_asyncio.fixture
async def engine():
    """In-memory async engine для каждого теста.

    StaticPool + check_same_thread=False заставляют все сессии
    использовать одно подключение — иначе in-memory SQLite создаст
    отдельную пустую БД для каждого нового connection.
    """

    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def session_maker(engine):
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def db_session(session_maker, monkeypatch):
    """Патчит async_session во всех модулях сервиса."""

    for target in _PATCH_TARGETS:
        monkeypatch.setattr(target, "async_session", session_maker)

    return session_maker


@pytest_asyncio.fixture
async def seed_data(db_session):
    """Заполняет тестовую БД каталогом и возвращает справочник ID."""

    session_maker = db_session

    async with session_maker() as session:
        session.add_all([
            Category(id=1, name="Свечи", emoji="🕯"),
            Category(id=2, name="Диффузоры", emoji="🏠"),
        ])

        session.add_all([
            Product(
                id=1,
                category_id=1,
                name="Кашемир",
                description="Теплый аромат",
                variants=[
                    ProductVariant(id=1, volume="75 г", price=450, burn="10 часов"),
                    ProductVariant(id=2, volume="200 г", price=990, burn="45 часов"),
                ],
            ),
            Product(
                id=2,
                category_id=1,
                name="Белый чай",
                description="Свежий аромат",
                is_active=False,
                variants=[
                    ProductVariant(id=3, volume="100 г", price=550),
                ],
            ),
            Product(
                id=3,
                category_id=2,
                name="Диффузор Кашемир",
                description="Для дома",
                variants=[
                    ProductVariant(id=4, volume="100 мл", price=1290),
                ],
            ),
        ])

        await session.commit()

    return {
        "category_ids": [1, 2],
        "product_ids": [1, 2, 3],
        "variant_ids": [1, 2, 3, 4],
        "active_product_ids": [1, 3],
    }
