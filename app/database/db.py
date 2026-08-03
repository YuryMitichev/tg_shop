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
    ("orders", "payment_method", "TEXT NOT NULL DEFAULT 'manual'"),
    ("shops", "delivery_enabled", "BOOLEAN NOT NULL DEFAULT 1"),
    ("shops", "courier_services", "TEXT NOT NULL DEFAULT '[]'"),
    ("shops", "product_attrs", "TEXT NOT NULL DEFAULT '[\"volume\"]'"),
    ("product_variants", "size", "TEXT"),
    ("product_variants", "color", "TEXT"),
    ("product_variants", "scent", "TEXT"),
    ("product_variants", "dimensions", "TEXT"),
    ("shops", "company_name", "TEXT"),
    ("shops", "company_inn", "TEXT"),
    ("shops", "company_address", "TEXT"),
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


def _rebuild_unique_tables(conn) -> None:
    """Пересоздаёт таблицы с уникальными constraint'ами для мультитенантности.

    В SQLite нельзя ALTER COLUMN — нужно пересоздать таблицу.
    Проверяем по наличию старого UNIQUE на telegram_user_id.
    """
    from sqlalchemy import text, inspect

    insp = inspect(conn)
    existing_tables = insp.get_table_names()

    for table_name, recreate_sql, insert_sql in [        (
            "user_profiles",
            """CREATE TABLE user_profiles_new (
                id INTEGER PRIMARY KEY,
                shop_id INTEGER REFERENCES shops(id),
                telegram_user_id INTEGER,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                notes TEXT,
                tags TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME,
                UNIQUE(shop_id, telegram_user_id)
            )""",
            """INSERT INTO user_profiles_new (id, shop_id, telegram_user_id, username, first_name, last_name, phone, notes, tags, created_at, last_seen)
               SELECT id, shop_id, telegram_user_id, username, first_name, last_name, phone, notes, tags, created_at, last_seen FROM user_profiles""",
        ),
        (
            "admin_users",
            """CREATE TABLE admin_users_new (
                id INTEGER PRIMARY KEY,
                shop_id INTEGER REFERENCES shops(id),
                telegram_user_id INTEGER,
                display_name TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(shop_id, telegram_user_id)
            )""",
            """INSERT INTO admin_users_new (id, shop_id, telegram_user_id, display_name, created_at)
               SELECT id, shop_id, telegram_user_id, display_name, created_at FROM admin_users""",
        ),
    ]:
        if table_name not in existing_tables:
            continue

        cols = {c["name"] for c in insp.get_columns(table_name)}
        if "shop_id" not in cols:
            continue

        result = conn.execute(text(f"PRAGMA index_list({table_name})")).fetchall()
        has_old_unique = any(
            "telegram_user_id" in str(conn.execute(text(f"PRAGMA index_info({r[1]})")).fetchall())
            for r in result
            if r[2] == 1
        )

        if not has_old_unique:
            continue

        conn.execute(text(recreate_sql))
        conn.execute(text(insert_sql))
        conn.execute(text(f"DROP TABLE {table_name}"))
        conn.execute(text(f"ALTER TABLE {table_name}_new RENAME TO {table_name}"))


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

        await conn.run_sync(_rebuild_unique_tables)

    from app.services.subscription_service import SubscriptionService
    await SubscriptionService.ensure_default_plans()
