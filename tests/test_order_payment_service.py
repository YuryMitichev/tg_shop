import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.payment import Payment
from app.services.order_payment_service import OrderPaymentService


@pytest.fixture
async def order_in_db(db_session, seed_data):
    """Создаёт заказ напрямую в БД."""
    from app.models.order import Order

    async with db_session() as session:
        order = Order(
            id=100,
            shop_id=1,
            telegram_user_id=123456,
            status="new",
            full_name="Тест Тестов",
            phone="+79991234567",
            address="",
            total_amount=1500,
            payment_method="yookassa",
        )
        session.add(order)
        await session.commit()
    return 100


_YK_CREDS = ("test_yk_shop_id", "test_yk_secret_key")


class TestCreatePayment:

    async def test_create_payment_success(self, db_session, seed_data, order_in_db):
        mock_response = {
            "payment_id": "yk_order_test",
            "confirmation_url": "https://yoomoney.ru/checkout?id=order123",
        }

        with patch(
            "app.services.order_payment_service.YooKassaClient.create_payment",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.services.order_payment_service.ShopService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=_YK_CREDS,
        ):
            result = await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

        assert result is not None
        assert result["payment_id"] == "yk_order_test"
        assert "yoomoney.ru" in result["confirmation_url"]

    async def test_create_payment_order_not_found(self, db_session, seed_data):
        result = await OrderPaymentService.create_payment(shop_id=1, order_id=999)
        assert result is None

    async def test_create_payment_wrong_shop(self, db_session, seed_data, order_in_db):
        result = await OrderPaymentService.create_payment(shop_id=999, order_id=order_in_db)
        assert result is None

    async def test_create_payment_no_yookassa_credentials(
        self, db_session, seed_data, order_in_db
    ):
        with patch(
            "app.services.order_payment_service.ShopService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

        assert result is None

    async def test_create_payment_yookassa_fails(self, db_session, seed_data, order_in_db):
        with patch(
            "app.services.order_payment_service.YooKassaClient.create_payment",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.services.order_payment_service.ShopService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=_YK_CREDS,
        ):
            result = await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

        assert result is None

    async def test_create_payment_metadata_has_type_order(
        self, db_session, seed_data, order_in_db
    ):
        captured = {}

        async def fake_create(amount_rub, description, return_url, metadata, **kwargs):
            captured["metadata"] = metadata
            captured["kwargs"] = kwargs
            return {"payment_id": "yk_x", "confirmation_url": "https://yoomoney.ru/x"}

        with patch(
            "app.services.order_payment_service.YooKassaClient.create_payment",
            new=fake_create,
        ), patch(
            "app.services.order_payment_service.ShopService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=_YK_CREDS,
        ):
            await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

        assert captured["metadata"]["type"] == "order"
        assert captured["metadata"]["order_id"] == str(order_in_db)
        assert captured["metadata"]["shop_id"] == "1"
        assert captured["kwargs"]["shop_id"] == "test_yk_shop_id"
        assert captured["kwargs"]["secret_key"] == "test_yk_secret_key"


class TestPaymentIdempotency:

    @staticmethod
    def _mock_yk(creds=True, response=None):
        """Возвращает pair of context managers: (client_patch, creds_patch)."""
        return (
            patch(
                "app.services.order_payment_service.YooKassaClient.create_payment",
                new_callable=AsyncMock,
                return_value=response,
            ),
            patch(
                "app.services.order_payment_service.ShopService.get_yookassa_credentials",
                new_callable=AsyncMock,
                return_value=_YK_CREDS if creds else None,
            ),
        )

    async def test_retry_reuses_idempotency_key(
        self, db_session, seed_data, order_in_db
    ):
        keys = []

        async def fake_create(amount_rub, description, return_url, metadata, **kwargs):
            keys.append(kwargs.get("idempotency_key"))
            return {
                "payment_id": f"yk_{len(keys)}",
                "confirmation_url": f"https://yoomoney.ru/{len(keys)}",
            }

        with patch(
            "app.services.order_payment_service.YooKassaClient.create_payment",
            new=fake_create,
        ), patch(
            "app.services.order_payment_service.ShopService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=_YK_CREDS,
        ):
            await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)
            await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

        assert len(keys) == 2
        assert keys[0] == keys[1] == f"order:{order_in_db}:yookassa"

    async def test_single_payment_row_on_retry(self, db_session, seed_data, order_in_db):
        from app.models.order import Order

        client_patch, creds_patch = self._mock_yk(
            response={
                "payment_id": "yk_stable",
                "confirmation_url": "https://yoomoney.ru/stable",
            }
        )
        with client_patch, creds_patch:
            await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)
            await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

        async with db_session() as session:
            result = await session.execute(select(Payment))
            payments = result.scalars().all()

            assert len(payments) == 1
            assert payments[0].idempotency_key == f"order:{order_in_db}:yookassa"
            assert payments[0].provider_payment_id == "yk_stable"
            assert payments[0].status == "pending"

            order = await session.get(Order, order_in_db)
            assert order.payment_id == "yk_stable"

    async def test_timeout_then_retry_no_second_intent(
        self, db_session, seed_data, order_in_db
    ):
        keys = []

        async def fake_create(amount_rub, description, return_url, metadata, **kwargs):
            keys.append(kwargs.get("idempotency_key"))
            if len(keys) == 1:
                return None
            return {
                "payment_id": "yk_recovered",
                "confirmation_url": "https://yoomoney.ru/recovered",
            }

        with patch(
            "app.services.order_payment_service.YooKassaClient.create_payment",
            new=fake_create,
        ), patch(
            "app.services.order_payment_service.ShopService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=_YK_CREDS,
        ):
            first = await OrderPaymentService.create_payment(
                shop_id=1, order_id=order_in_db
            )
            second = await OrderPaymentService.create_payment(
                shop_id=1, order_id=order_in_db
            )

        assert first is None
        assert second is not None
        assert second["payment_id"] == "yk_recovered"
        assert len(keys) == 2
        assert keys[0] == keys[1]

        async with db_session() as session:
            result = await session.execute(select(Payment))
            payments = result.scalars().all()

            assert len(payments) == 1
            assert payments[0].provider_payment_id == "yk_recovered"
            assert payments[0].status == "pending"

    async def test_unique_constraint_rejects_duplicate_key(
        self, db_session, seed_data, order_in_db
    ):
        row_kwargs = dict(
            order_id=order_in_db,
            shop_id=1,
            provider="yookassa",
            attempt=1,
            idempotency_key="order:duplicate:yookassa",
            amount_minor=150000,
            currency="RUB",
            status="pending",
        )

        async with db_session() as session:
            session.add(Payment(**row_kwargs))
            await session.commit()

            session.add(Payment(**row_kwargs))
            with pytest.raises(IntegrityError):
                await session.commit()

    async def test_concurrent_create_single_intent(
        self, db_session, seed_data, order_in_db
    ):
        keys = []
        tx1_committed = asyncio.Event()

        async def slow_fake_create(amount_rub, description, return_url, metadata, **kwargs):
            # Мок вызывается только ПОСЛЕ фиксации TX1 (insert payments),
            # поэтому событие означает: строка платежа уже закоммичена
            keys.append(kwargs.get("idempotency_key"))
            tx1_committed.set()
            await asyncio.sleep(0.05)
            return {
                "payment_id": "yk_concurrent",
                "confirmation_url": "https://yoomoney.ru/concurrent",
            }

        async def second_request():
            # B стартует, пока A ждёт ответ внешнего API:
            # классический double-click / сетевой retry
            await tx1_committed.wait()
            return await OrderPaymentService.create_payment(
                shop_id=1, order_id=order_in_db
            )

        with patch(
            "app.services.order_payment_service.YooKassaClient.create_payment",
            new=slow_fake_create,
        ), patch(
            "app.services.order_payment_service.ShopService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=_YK_CREDS,
        ):
            results = await asyncio.gather(
                OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db),
                second_request(),
            )

        assert all(r is not None for r in results)

        async with db_session() as session:
            result = await session.execute(select(Payment))
            payments = result.scalars().all()

            assert len(payments) == 1
            assert payments[0].provider_payment_id == "yk_concurrent"
            assert len(set(keys)) == 1
            assert keys[0] == f"order:{order_in_db}:yookassa"

    async def test_succeeded_payment_not_recreated(
        self, db_session, seed_data, order_in_db
    ):
        async with db_session() as session:
            session.add(
                Payment(
                    order_id=order_in_db,
                    shop_id=1,
                    provider="yookassa",
                    idempotency_key=f"order:{order_in_db}:yookassa",
                    provider_payment_id="yk_done",
                    amount_minor=150000,
                    currency="RUB",
                    status="succeeded",
                )
            )
            await session.commit()

        client_patch, creds_patch = self._mock_yk(
            response={
                "payment_id": "yk_should_not_happen",
                "confirmation_url": "https://yoomoney.ru/never",
            }
        )
        with client_patch as client_mock, creds_patch:
            result = await OrderPaymentService.create_payment(
                shop_id=1, order_id=order_in_db
            )

        client_mock.assert_not_awaited()
        assert result == {"payment_id": "yk_done", "confirmation_url": None}

    async def test_webhook_marks_payment_succeeded(
        self, db_session, seed_data, order_in_db
    ):
        client_patch, creds_patch = self._mock_yk(
            response={
                "payment_id": "yk_hook_ok",
                "confirmation_url": "https://yoomoney.ru/hook",
            }
        )
        with client_patch, creds_patch:
            await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_hook_ok",
                "status": "succeeded",
                "amount": {"value": "1500.00", "currency": "RUB"},
                "metadata": {
                    "type": "order",
                    "shop_id": "1",
                    "order_id": str(order_in_db),
                },
            },
        }

        with patch.object(
            OrderPaymentService,
            "_notify_user",
            new_callable=AsyncMock,
        ):
            result = await OrderPaymentService.process_webhook(data)

        assert result is True

        async with db_session() as session:
            payment = await session.execute(
                select(Payment).where(
                    Payment.provider_payment_id == "yk_hook_ok"
                )
            )
            payment = payment.scalar_one()
            assert payment.status == "succeeded"

    async def test_webhook_canceled_marks_payment_canceled(
        self, db_session, seed_data, order_in_db
    ):
        client_patch, creds_patch = self._mock_yk(
            response={
                "payment_id": "yk_hook_cancel",
                "confirmation_url": "https://yoomoney.ru/cancel",
            }
        )
        with client_patch, creds_patch:
            await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

        data = {
            "event": "payment.canceled",
            "object": {
                "id": "yk_hook_cancel",
                "metadata": {
                    "type": "order",
                    "shop_id": "1",
                    "order_id": str(order_in_db),
                },
            },
        }

        result = await OrderPaymentService.process_webhook(data)

        assert result is True

        async with db_session() as session:
            payment = await session.execute(
                select(Payment).where(
                    Payment.provider_payment_id == "yk_hook_cancel"
                )
            )
            payment = payment.scalar_one()
            assert payment.status == "canceled"


class TestPaymentAttempts:

    async def test_new_attempt_after_canceled_payment(
        self, db_session, seed_data, order_in_db
    ):
        from app.models.order import Order

        keys = []

        async def fake_create(amount_rub, description, return_url, metadata, **kwargs):
            keys.append(kwargs.get("idempotency_key"))
            n = len(keys)
            return {
                "payment_id": f"yk_attempt_{n}",
                "confirmation_url": f"https://yoomoney.ru/attempt_{n}",
            }

        with patch(
            "app.services.order_payment_service.YooKassaClient.create_payment",
            new=fake_create,
        ), patch(
            "app.services.order_payment_service.ShopService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=_YK_CREDS,
        ):
            r1 = await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

            canceled = await OrderPaymentService.process_webhook({
                "event": "payment.canceled",
                "object": {
                    "id": "yk_attempt_1",
                    "metadata": {
                        "type": "order",
                        "shop_id": "1",
                        "order_id": str(order_in_db),
                    },
                },
            })

            r2 = await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

        assert canceled is True
        assert keys[0] == f"order:{order_in_db}:yookassa"
        assert keys[1] == f"order:{order_in_db}:yookassa:2"
        assert keys[0] != keys[1]
        assert r2["payment_id"] == "yk_attempt_2"

        async with db_session() as session:
            result = await session.execute(
                select(Payment).order_by(Payment.attempt)
            )
            payments = result.scalars().all()

            assert len(payments) == 2
            assert [p.attempt for p in payments] == [1, 2]
            assert payments[0].status == "canceled"
            assert payments[1].status == "pending"
            assert payments[1].provider_payment_id == "yk_attempt_2"

            order = await session.get(Order, order_in_db)
            assert order.payment_id == "yk_attempt_2"

    async def test_pending_attempt_reused_not_incremented(
        self, db_session, seed_data, order_in_db
    ):
        client_patch, creds_patch = TestPaymentIdempotency._mock_yk(
            response={
                "payment_id": "yk_p1",
                "confirmation_url": "https://yoomoney.ru/p1",
            }
        )
        with client_patch, creds_patch:
            await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)
            await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

        async with db_session() as session:
            result = await session.execute(select(Payment))
            payments = result.scalars().all()

            assert len(payments) == 1
            assert payments[0].attempt == 1
            assert payments[0].idempotency_key == f"order:{order_in_db}:yookassa"

    async def test_concurrent_new_attempt_after_cancel_single_row(
        self, db_session, seed_data, order_in_db
    ):
        async with db_session() as session:
            session.add(
                Payment(
                    order_id=order_in_db,
                    shop_id=1,
                    provider="yookassa",
                    attempt=1,
                    idempotency_key=f"order:{order_in_db}:yookassa",
                    provider_payment_id="yk_old_canceled",
                    amount_minor=150000,
                    currency="RUB",
                    status="canceled",
                )
            )
            await session.commit()

        keys = []
        attempt2_inserted = asyncio.Event()

        async def fake_create(amount_rub, description, return_url, metadata, **kwargs):
            keys.append(kwargs.get("idempotency_key"))
            attempt2_inserted.set()
            await asyncio.sleep(0.05)
            return {
                "payment_id": "yk_attempt_2",
                "confirmation_url": "https://yoomoney.ru/attempt_2",
            }

        async def second_request():
            await attempt2_inserted.wait()
            return await OrderPaymentService.create_payment(
                shop_id=1, order_id=order_in_db
            )

        with patch(
            "app.services.order_payment_service.YooKassaClient.create_payment",
            new=fake_create,
        ), patch(
            "app.services.order_payment_service.ShopService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=_YK_CREDS,
        ):
            results = await asyncio.gather(
                OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db),
                second_request(),
            )

        assert all(r is not None for r in results)
        assert len(set(keys)) == 1
        assert keys[0] == f"order:{order_in_db}:yookassa:2"

        async with db_session() as session:
            result = await session.execute(
                select(Payment).where(Payment.attempt == 2)
            )
            attempt2_rows = result.scalars().all()
            assert len(attempt2_rows) == 1
            assert attempt2_rows[0].status == "pending"

    async def test_attempt_unique_constraint(
        self, db_session, seed_data, order_in_db
    ):
        kwargs = dict(
            order_id=order_in_db,
            shop_id=1,
            provider="yookassa",
            amount_minor=150000,
            currency="RUB",
            status="pending",
        )

        async with db_session() as session:
            session.add(Payment(attempt=1, idempotency_key="k_a1", **kwargs))
            await session.commit()

            session.add(Payment(attempt=1, idempotency_key="k_a1_other", **kwargs))
            with pytest.raises(IntegrityError):
                await session.commit()

    async def test_terminal_order_status_blocks_payment(
        self, db_session, seed_data, order_in_db
    ):
        from app.models.order import Order

        async with db_session() as session:
            order = await session.get(Order, order_in_db)
            order.status = "cancelled"
            await session.commit()

        client_patch, creds_patch = TestPaymentIdempotency._mock_yk(
            response={
                "payment_id": "yk_should_not_happen",
                "confirmation_url": "https://yoomoney.ru/never",
            }
        )
        with client_patch as client_mock, creds_patch:
            result = await OrderPaymentService.create_payment(
                shop_id=1, order_id=order_in_db
            )

        client_mock.assert_not_awaited()
        assert result is None


class TestProcessWebhook:

    async def test_payment_succeeded_marks_paid(
        self, db_session, seed_data, order_in_db
    ):
        from app.models.order import Order

        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_paid_123",
                "status": "succeeded",
                "amount": {"value": "1500.00", "currency": "RUB"},
                "metadata": {
                    "type": "order",
                    "shop_id": "1",
                    "order_id": str(order_in_db),
                },
            },
        }

        with patch.object(
            OrderPaymentService,
            "_notify_user",
            new_callable=AsyncMock,
        ):
            result = await OrderPaymentService.process_webhook(data)

        assert result is True

        async with db_session() as session:
            order = await session.get(Order, order_in_db)
            assert order.status == "paid"
            assert order.payment_id == "yk_paid_123"

    async def test_payment_succeeded_wrong_amount(
        self, db_session, seed_data, order_in_db
    ):
        from app.models.order import Order

        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_wrong",
                "status": "succeeded",
                "amount": {"value": "999.00", "currency": "RUB"},
                "metadata": {
                    "type": "order",
                    "shop_id": "1",
                    "order_id": str(order_in_db),
                },
            },
        }

        result = await OrderPaymentService.process_webhook(data)

        assert result is False

        async with db_session() as session:
            order = await session.get(Order, order_in_db)
            assert order.status == "new"

    async def test_payment_canceled(self, db_session, seed_data, order_in_db):
        data = {
            "event": "payment.canceled",
            "object": {
                "id": "yk_cancel",
                "metadata": {
                    "type": "order",
                    "shop_id": "1",
                    "order_id": str(order_in_db),
                },
            },
        }

        result = await OrderPaymentService.process_webhook(data)
        assert result is True

    async def test_unknown_event_ignored(self, db_session, seed_data, order_in_db):
        data = {
            "event": "payment.waiting_for_capture",
            "object": {
                "id": "yk_wait",
                "metadata": {
                    "type": "order",
                    "shop_id": "1",
                    "order_id": str(order_in_db),
                },
            },
        }

        result = await OrderPaymentService.process_webhook(data)
        assert result is True

    async def test_order_not_found(self, db_session, seed_data):
        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_ghost",
                "amount": {"value": "100.00", "currency": "RUB"},
                "metadata": {
                    "type": "order",
                    "shop_id": "1",
                    "order_id": "99999",
                },
            },
        }

        with patch.object(
            OrderPaymentService,
            "_notify_user",
            new_callable=AsyncMock,
        ):
            result = await OrderPaymentService.process_webhook(data)

        assert result is False

    async def test_no_metadata(self, db_session, seed_data):
        result = await OrderPaymentService.process_webhook({"foo": "bar"})
        assert result is False

    async def test_already_paid_not_overwritten(
        self, db_session, seed_data, order_in_db
    ):
        from app.models.order import Order

        async with db_session() as session:
            order = await session.get(Order, order_in_db)
            order.status = "done"
            await session.commit()

        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_late",
                "amount": {"value": "1500.00", "currency": "RUB"},
                "metadata": {
                    "type": "order",
                    "shop_id": "1",
                    "order_id": str(order_in_db),
                },
            },
        }

        with patch.object(
            OrderPaymentService,
            "_notify_user",
            new_callable=AsyncMock,
        ):
            await OrderPaymentService.process_webhook(data)

        async with db_session() as session:
            order = await session.get(Order, order_in_db)
            assert order.status == "done"


class TestMultiConnectionConcurrency:
    """Файловая SQLite с РАЗДЕЛЬНЫМИ соединениями (не StaticPool).

    Локальная проверка прод-механики: транзакции A и B изолированы,
    rollback B не затрагивает TX A, конфликт ловится UNIQUE-констрейнтом.
    Полный аналог на PostgreSQL — tests/test_payment_pg_concurrency.py
    (запускается при PG_TEST_DATABASE_URL / в CI).
    """

    @staticmethod
    async def _make_engine_and_maker(tmp_path, monkeypatch):
        from sqlalchemy.ext.asyncio import (
            async_sessionmaker,
            create_async_engine,
        )

        from app.database.db import Base
        from app.models.order import Order
        from app.models.shop import Shop
        from app.services import order_payment_service as ops_module

        db_file = (tmp_path / "conc.db").as_posix()
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        maker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(ops_module, "async_session", maker)

        async with maker() as session:
            session.add(
                Shop(
                    id=1,
                    name="Conc Shop",
                    bot_token="conc:token",
                    bot_token_hash="hash",
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
                    full_name="Conc",
                    phone="+70000000000",
                    address="",
                    total_amount=1500,
                    payment_method="yookassa",
                )
            )
            await session.commit()

        return maker

    async def test_duplicate_insert_rollback_isolation(
        self, tmp_path, monkeypatch
    ):
        maker = await self._make_engine_and_maker(tmp_path, monkeypatch)

        key = "order:100:yookassa"
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

        a_flushed = asyncio.Event()

        async def request_a():
            async with maker() as session:
                session.add(Payment(**row_kwargs))
                await session.flush()
                a_flushed.set()
                await asyncio.sleep(0.2)
                await session.commit()

        async def request_b():
            await a_flushed.wait()
            await asyncio.sleep(0.05)
            async with maker() as session:
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

        async with maker() as session:
            rows = (
                await session.execute(select(Payment).where(Payment.order_id == 100))
            ).scalars().all()
            assert len(rows) == 1

    async def test_concurrent_service_calls_single_intent(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        from app.services import order_payment_service as ops_module

        maker = await self._make_engine_and_maker(tmp_path, monkeypatch)

        keys = []

        async def fake_create(amount_rub, description, return_url, metadata, **kwargs):
            keys.append(kwargs.get("idempotency_key"))
            await asyncio.sleep(0.05)
            return {
                "payment_id": "yk_conc",
                "confirmation_url": "https://yoomoney.ru/conc",
            }

        monkeypatch.setattr(
            ops_module,
            "YooKassaClient",
            SimpleNamespace(create_payment=fake_create),
        )
        monkeypatch.setattr(
            ops_module,
            "ShopService",
            SimpleNamespace(
                get_yookassa_credentials=AsyncMock(return_value=_YK_CREDS)
            ),
        )

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

        async with maker() as session:
            rows = (
                await session.execute(select(Payment).where(Payment.order_id == 100))
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].provider_payment_id == "yk_conc"
