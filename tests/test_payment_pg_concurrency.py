"""Интеграционные тесты идемпотентности payments на реальном PostgreSQL.

SQLite/StaticPool в базовом suite делит одно соединение между сессиями,
что не доказывает реальную конкурентность. Эти тесты используют
отдельные pooled-соединения PostgreSQL и запускаются ТОЛЬКО при
заданном PG_TEST_DATABASE_URL, например:

    docker run -d --name pg-test -e POSTGRES_PASSWORD=test \\
        -e POSTGRES_DB=tgshop_test -p 5433:5432 postgres:16
    $env:PG_TEST_DATABASE_URL = "postgresql+asyncpg://postgres:test@localhost:5433/tgshop_test"
    python -m pytest tests/test_payment_pg_concurrency.py -v

В CI (ci.yml) поднимается сервис postgres и переменная задаётся автоматически.
Продакшн-код не изменяется — модуль содержит только тесты.
"""
import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.db import Base
import app.models  # noqa: F401 — регистрирует таблицы в metadata
from app.models.order import Order
from app.models.payment import Payment
from app.services import order_payment_service
from app.services.order_payment_service import OrderPaymentService
from app.utils.crypto import encrypt, token_hash

PG_TEST_DATABASE_URL = os.environ.get("PG_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not PG_TEST_DATABASE_URL,
    reason="задайте PG_TEST_DATABASE_URL для запуска PostgreSQL-тестов",
)

_YK_CREDS = ("pg_shop_id", "pg_secret_key")


@pytest_asyncio.fixture
async def pg_engine():
    engine = create_async_engine(PG_TEST_DATABASE_URL, pool_size=10)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session_maker(pg_engine, monkeypatch):
    maker = async_sessionmaker(bind=pg_engine, expire_on_commit=False)
    monkeypatch.setattr(order_payment_service, "async_session", maker)
    return maker


@pytest_asyncio.fixture
async def pg_order(pg_session_maker):
    from app.models.shop import Shop

    async with pg_session_maker() as session:
        session.add(
            Shop(
                id=1,
                name="PG Test Shop",
                bot_token=encrypt("pg:test"),
                bot_token_hash=token_hash("pg:test"),
                owner_telegram_id=1,
            )
        )
        await session.commit()
        session.add(
            Order(
                id=100,
                shop_id=1,
                telegram_user_id=1,
                status="new",
                full_name="PG Test",
                phone="+70000000000",
                address="",
                total_amount=1500,
                payment_method="yookassa",
            )
        )
        await session.commit()


class TestPGUniqueConflict:
    """A: INSERT key K (hold) → B: INSERT same K → A commit → B conflict → B re-select."""

    async def test_unique_conflict_and_recovery(
        self, pg_session_maker, pg_order
    ):
        key = "order:100:yookassa"
        a_flushed = asyncio.Event()

        row_kwargs = dict(
            order_id=100,
            shop_id=1,
            provider="yookassa",
            attempt=1,
            idempotency_key=key,
            amount_minor=150000,
            currency="RUB",
            status="pending",
        )

        async def request_a():
            async with pg_session_maker() as session:
                session.add(Payment(**row_kwargs))
                # INSERT выполнен, транзакция ещё открыта — B заблокируется
                await session.flush()
                a_flushed.set()
                await asyncio.sleep(0.2)
                await session.commit()

        async def request_b():
            await a_flushed.wait()
            await asyncio.sleep(0.05)
            async with pg_session_maker() as session:
                session.add(Payment(**row_kwargs))
                try:
                    await session.commit()
                    return "unexpectedly_committed"
                except IntegrityError:
                    await session.rollback()
                    row = (
                        await session.execute(
                            select(Payment).where(Payment.idempotency_key == key)
                        )
                    ).scalar_one()
                    return row

        _, b_result = await asyncio.wait_for(
            asyncio.gather(request_a(), request_b()), timeout=15
        )

        assert b_result != "unexpectedly_committed"
        assert b_result.idempotency_key == key
        assert b_result.status == "pending"

        async with pg_session_maker() as session:
            rows = (
                await session.execute(
                    select(Payment).where(Payment.order_id == 100)
                )
            ).scalars().all()
            assert len(rows) == 1


class TestPGServiceConcurrency:
    """Два конкурентных OrderPaymentService.create_payment на реальном PG."""

    @staticmethod
    def _patch_provider(monkeypatch, keys):
        async def fake_create(amount_rub, description, return_url, metadata, **kwargs):
            keys.append(kwargs.get("idempotency_key"))
            await asyncio.sleep(0.05)
            return {
                "payment_id": "yk_pg",
                "confirmation_url": "https://yoomoney.ru/pg",
            }

        monkeypatch.setattr(
            order_payment_service,
            "YooKassaClient",
            SimpleNamespace(create_payment=fake_create),
        )
        monkeypatch.setattr(
            order_payment_service,
            "ShopService",
            SimpleNamespace(
                get_yookassa_credentials=AsyncMock(return_value=_YK_CREDS)
            ),
        )

    async def test_concurrent_create_single_intent(
        self, pg_session_maker, pg_order, monkeypatch
    ):
        keys = []
        self._patch_provider(monkeypatch, keys)

        results = await asyncio.wait_for(
            asyncio.gather(
                OrderPaymentService.create_payment(shop_id=1, order_id=100),
                OrderPaymentService.create_payment(shop_id=1, order_id=100),
            ),
            timeout=15,
        )

        assert all(r is not None for r in results)
        assert len(set(keys)) == 1
        assert keys[0] == "order:100:yookassa"

        async with pg_session_maker() as session:
            rows = (
                await session.execute(
                    select(Payment).where(Payment.order_id == 100)
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].provider_payment_id == "yk_pg"

    async def test_canceled_then_new_attempt_on_pg(
        self, pg_session_maker, pg_order, monkeypatch
    ):
        keys = []
        self._patch_provider(monkeypatch, keys)

        await OrderPaymentService.create_payment(shop_id=1, order_id=100)

        canceled = await OrderPaymentService.process_webhook({
            "event": "payment.canceled",
            "object": {
                "id": "yk_pg",
                "metadata": {"type": "order", "shop_id": "1", "order_id": "100"},
            },
        })
        assert canceled is True

        r2 = await OrderPaymentService.create_payment(shop_id=1, order_id=100)

        assert r2 is not None
        assert keys[0] == "order:100:yookassa"
        assert keys[1] == "order:100:yookassa:2"

        async with pg_session_maker() as session:
            rows = (
                await session.execute(
                    select(Payment).where(Payment.order_id == 100).order_by(Payment.attempt)
                )
            ).scalars().all()
            assert [p.attempt for p in rows] == [1, 2]
            assert rows[0].status == "canceled"
            assert rows[1].status == "pending"
