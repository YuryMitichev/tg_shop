import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-pytest")

from cryptography.fernet import Fernet

_test_key = Fernet.generate_key().decode()
os.environ.setdefault("ENCRYPTION_KEY", _test_key)

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.database.db as db_module
import app.services.catalog_admin_service as catalog_admin_service
import app.services.order_admin_service as order_admin_service
import app.services.review_admin_service as review_admin_service
import app.services.stats_service as stats_service
import app.services.admin_user_service as admin_user_service
import app.services.cart_service as cart_service
import app.services.catalog_service as catalog_service
import app.services.crm_service as crm_service
import app.services.order_service as order_service
import app.services.review_service as review_service
import app.services.promo_service as promo_service
import app.services.broadcast_service as broadcast_service
import app.services.offer_service as offer_service
import app.services.shop_service as shop_service
import app.services.subscription_service as subscription_service
import app.services.order_payment_service as order_payment_service
import app.services.admin_auth_service as admin_auth_service
import app.services.message_service as message_service
import app.services.catalog_import_service as catalog_import_service
import app.services.product_attr_service as product_attr_service
import app.services.offer_agreement_service as offer_agreement_service
import app.services.legal_document_service as legal_document_service
import app.services.platform_settings_service as platform_settings_service
import app.services.channel_import_service as channel_import_service
import app.services.channel_import_worker as channel_import_worker
import app.services.channel_post_button_service as channel_post_button_service
import app.services.channel_post_button_worker as channel_post_button_worker
import app.services.channel_storefront_service as channel_storefront_service
import app.services.channel_backfill_service as channel_backfill_service
import app.services.channel_attribution_service as channel_attribution_service
import app.services.channel_metrics_service as channel_metrics_service
from app.services.admin_auth_service import AdminAuthService
from app.database.db import Base
from app.models import (  # noqa: F401 — импорт регистрирует таблицы в metadata
    CartItem,
    Category,
    Order,
    OrderItem,
    Product,
    ProductAttributeDef,
    OfferAcceptance,
    ShopOfferAcceptance,
    ProductPhoto,
    ProductVariant,
    Review,
    PromoCode,
    AdminUser,
    LoginToken,
    UserProfile,
    CommunicationLog,
    Broadcast,
    UserOffer,
)
from app.models.shop import Shop
from app.models.subscription import Subscription, SubscriptionPlan  # noqa: F401
from app.utils.crypto import encrypt, token_hash
from app.services.stats_service import StatsService
from app.services.subscription_service import SubscriptionService
from app.api.rate_limit import limiter



TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def _clear_service_caches():
    """Очищает TTL-кэши сервисов перед каждым тестом."""
    AdminAuthService._token_cache.clear()
    SubscriptionService._active_cache.clear()
    StatsService._stats_cache.clear()
    StatsService._chart_cache.clear()
    StatsService._analytics_cache.clear()
    limiter.reset()


_PATCH_TARGETS = [
    db_module,
    catalog_service,
    cart_service,
    order_service,
    catalog_admin_service,
    order_admin_service,
    review_admin_service,
    stats_service,
    admin_user_service,
    crm_service,
    review_service,
    promo_service,
    broadcast_service,
    offer_service,
    shop_service,
    subscription_service,
    order_payment_service,
    admin_auth_service,
    message_service,
    catalog_import_service,
    product_attr_service,
    offer_agreement_service,
    legal_document_service,
    platform_settings_service,
    channel_import_service,
    channel_import_worker,
    channel_post_button_service,
    channel_post_button_worker,
    channel_storefront_service,
    channel_backfill_service,
    channel_attribution_service,
    channel_metrics_service,
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
        session.add(Shop(id=1, name="Test Shop", bot_token=encrypt("test:token"), bot_token_hash=token_hash("test:token"), owner_telegram_id=1))

        session.add_all([
            Category(id=1, name="Свечи", emoji="🕯", shop_id=1),
            Category(id=2, name="Диффузоры", emoji="🏠", shop_id=1),
        ])

        session.add_all([
            Product(
                id=1,
                category_id=1,
                name="Кашемир",
                description="Теплый аромат",
                variants=[
                    ProductVariant(id=1, volume="75 г", price=450, stock=10, attributes={"burn": "10 часов"}),
                    ProductVariant(id=2, volume="200 г", price=990, stock=5, attributes={"burn": "45 часов"}),
                ],
            ),
            Product(
                id=2,
                category_id=1,
                name="Белый чай",
                description="Свежий аромат",
                is_active=False,
                variants=[
                    ProductVariant(id=3, volume="100 г", price=550, stock=0, attributes={}),
                ],
            ),
            Product(
                id=3,
                category_id=2,
                name="Диффузор Кашемир",
                description="Для дома",
                variants=[
                    ProductVariant(id=4, volume="100 мл", price=1290, stock=3, attributes={}),
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


# ==========================
# Фикстуры для HTTP API тестов
# ==========================

_ADMIN_DICT = {"admin_id": 123456, "shop_id": 1, "is_super_admin": False}


@pytest.fixture
def admin_cookie():
    """Возвращает dict cookie для HTTP-запросов к админ-API."""
    token = AdminAuthService._create_token(123456, shop_id=1, is_super_admin=False)
    return {"admin_token": token}


@pytest.fixture
def mock_admin_auth():
    """Подменяет проверку токена — возвращает тестового админа."""
    with patch(
        "app.api.admin_auth.AdminAuthService.verify_token",
        new_callable=AsyncMock,
        return_value=_ADMIN_DICT,
    ):
        yield


@pytest_asyncio.fixture
async def active_subscription(db_session):
    """Создаёт активную подписку для shop_id=1."""
    from app.models.subscription import Subscription, SubscriptionPlan

    session_maker = db_session
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with session_maker() as session:
        session.add(SubscriptionPlan(
            id=1, name="Тест", price=5000, duration_days=30, is_trial=False,
        ))
        await session.commit()
        session.add(Subscription(
            shop_id=1, plan_id=1, status="active",
            started_at=now, expires_at=now + timedelta(days=25),
        ))
        await session.commit()
