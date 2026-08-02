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


def _add_column_if_missing(conn, table: str, column: str, definition: str) -> None:
    """Добавляет колонку в таблицу, если её ещё нет (SQLite ALTER TABLE)."""
    from sqlalchemy import text, inspect

    inspector = inspect(conn)
    existing = [col["name"] for col in inspector.get_columns(table)]

    if column not in existing:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))


_MIGRATIONS = [
    ("product_variants", "stock", "INTEGER NOT NULL DEFAULT 0"),
    ("order_items", "variant_id", "INTEGER"),
    ("orders", "status_updated_at", "DATETIME"),
    ("categories", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("products", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("product_variants", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("product_photos", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("cart_items", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("orders", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("order_items", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("reviews", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("promo_codes", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("system_messages", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("admin_users", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("user_profiles", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("communication_logs", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("broadcasts", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
    ("user_offers", "shop_id", "INTEGER NOT NULL DEFAULT 1"),
]


def _ensure_default_shop(conn) -> None:
    """Создаёт магазин по умолчанию (id=1), если его ещё нет."""
    from sqlalchemy import text

    result = conn.execute(text("SELECT 1 FROM shops WHERE id = 1")).fetchone()
    if result is None:
        conn.execute(
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


async def init_db() -> None:
    """
    Создаёт таблицы в БД, если их ещё нет, и применяет миграции
    новых колонок к существующим таблицам (SQLite ALTER TABLE).
    """
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        await conn.run_sync(_ensure_default_shop)

        for table, column, definition in _MIGRATIONS:
            await conn.run_sync(_add_column_if_missing, table, column, definition)
