from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.utils.crypto import encrypt, token_hash


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""
    pass


DATABASE_URL = settings.database_url

_engine_kwargs = {"echo": False}

if DATABASE_URL.startswith("postgresql"):
    _engine_kwargs.update(
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """
    Заполняет БД стартовыми данными после применения миграций Alembic.

    Создаёт:
    — магазин по умолчанию (id=1) из переменных окружения;
    — тарифы подписок по умолчанию.

    Безопасно вызывать при каждом старте — существующие записи не затираются.
    """
    from sqlalchemy import text

    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM shops WHERE id = 1")
        )
        if result.first() is None:
            await conn.execute(
                text(
                    "INSERT INTO shops (id, name, bot_token, bot_token_hash, owner_telegram_id, is_active) "
                    "VALUES (1, :name, :token, :token_hash, :owner, TRUE)"
                ),
                {
                    "name": settings.shop_name,
                    "token": encrypt(settings.bot_token),
                    "token_hash": token_hash(settings.bot_token),
                    "owner": settings.admin_id_list[0] if settings.admin_id_list else 0,
                },
            )

    from app.services.subscription_service import SubscriptionService
    await SubscriptionService.ensure_default_plans()
