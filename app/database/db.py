from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""
    pass


DATABASE_URL = settings.database_url

engine = create_async_engine(DATABASE_URL, echo=False)

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
                    "INSERT INTO shops (id, name, bot_token, owner_telegram_id, is_active) "
                    "VALUES (1, :name, :token, :owner, 1)"
                ),
                {
                    "name": settings.shop_name,
                    "token": settings.bot_token,
                    "owner": settings.admin_id_list[0] if settings.admin_id_list else 0,
                },
            )

    from app.services.subscription_service import SubscriptionService
    await SubscriptionService.ensure_default_plans()
