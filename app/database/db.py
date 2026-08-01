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
]


async def init_db() -> None:
    """
    Создаёт таблицы в БД, если их ещё нет, и применяет миграции
    новых колонок к существующим таблицам (SQLite ALTER TABLE).
    """
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        for table, column, definition in _MIGRATIONS:
            await conn.run_sync(_add_column_if_missing, table, column, definition)
