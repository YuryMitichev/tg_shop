from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.main import create_app
from app.core.config import settings
from app.models.order import Order
from app.models.shop import Shop
from app.models.subscription import Subscription, SubscriptionPlan


@pytest.fixture
def yookassa_enabled(monkeypatch):
    """Включает ЮKassa в настройках на время теста."""
    monkeypatch.setattr(settings, "yookassa_shop_id", "test_shop")
    monkeypatch.setattr(settings, "yookassa_secret_key", "test_key")


@pytest.fixture
async def paid_order(db_session, seed_data):
    """Создаёт заказ в статусе 'new' для теста оплаты."""
    async with db_session() as session:
        order = Order(
            id=100,
            shop_id=1,
            telegram_user_id=111,
            status="new",
            full_name="Тест Тестов",
            phone="+7 999 000-00-00",
            address="г. Москва",
            total_amount=1500,
            payment_method="yookassa",
        )
        session.add(order)
        await session.commit()
    return 100


@pytest.fixture
async def trial_subscription(db_session, seed_data):
    """Создаёт триальную подписку и платный тариф."""
    async with db_session() as session:
        plan = SubscriptionPlan(
            id=10,
            name="Подписка — 1 месяц",
            price=5000,
            duration_days=30,
            is_trial=False,
            is_active=True,
        )
        session.add(plan)

        sub = Subscription(
            id=1,
            shop_id=1,
            plan_id=10,
            status="trial",
            started_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=14),
        )
        session.add(sub)
        await session.commit()
    return {"shop_id": 1, "plan_id": 10}


_YK_CREDS = ("test_shop_id", "test_secret_key")


class TestYooKassaWebhookOrder:
    """Вебхук ЮKassa — оплата заказа."""

    async def test_order_payment_succeeded(
        self, db_session, seed_data, yookassa_enabled, paid_order
    ):
        """Успешный платёж заказа — статус меняется на 'paid'."""
        verified = {
            "id": "pay-123",
            "status": "succeeded",
            "amount": {"value": "1500.00", "currency": "RUB"},
            "metadata": {"type": "order", "shop_id": "1", "order_id": "100"},
        }

        with patch(
            "app.api.routes.payments.YooKassaClient.get_payment",
            new_callable=AsyncMock,
            return_value=verified,
        ), patch(
            "app.api.routes.payments.ShopService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=_YK_CREDS,
        ), patch(
            "app.services.order_payment_service.OrderPaymentService._notify_user",
            new_callable=AsyncMock,
        ):
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/payments/yookassa/webhook",
                    json={
                        "event": "payment.succeeded",
                        "object": {
                            "id": "pay-123",
                            "metadata": {"type": "order", "shop_id": "1", "order_id": "100"},
                        },
                    },
                )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        async with db_session() as session:
            order = await session.get(Order, 100)
            assert order.status == "paid"
            assert order.payment_id == "pay-123"
            assert order.status_updated_at is not None

    async def test_order_already_paid(
        self, db_session, seed_data, yookassa_enabled, paid_order
    ):
        """Повторный вебхук по уже оплаченному заказу — статус не сбрасывается."""
        async with db_session() as session:
            order = await session.get(Order, 100)
            order.status = "done"
            await session.commit()

        verified = {
            "id": "pay-123",
            "status": "succeeded",
            "amount": {"value": "1500.00", "currency": "RUB"},
            "metadata": {"type": "order", "shop_id": "1", "order_id": "100"},
        }

        with patch(
            "app.api.routes.payments.YooKassaClient.get_payment",
            new_callable=AsyncMock,
            return_value=verified,
        ), patch(
            "app.api.routes.payments.ShopService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=_YK_CREDS,
        ), patch(
            "app.services.order_payment_service.OrderPaymentService._notify_user",
            new_callable=AsyncMock,
        ):
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/payments/yookassa/webhook",
                    json={
                        "event": "payment.succeeded",
                        "object": {
                            "id": "pay-123",
                            "metadata": {"type": "order", "shop_id": "1", "order_id": "100"},
                        },
                    },
                )

        assert resp.status_code == 200

        async with db_session() as session:
            order = await session.get(Order, 100)
            assert order.status == "done"

    async def test_order_not_found(
        self, db_session, seed_data, yookassa_enabled
    ):
        """Вебхук по несуществующему заказу — 200 OK, но без ошибки."""
        verified = {
            "id": "pay-404",
            "status": "succeeded",
            "amount": {"value": "100.00", "currency": "RUB"},
            "metadata": {"type": "order", "shop_id": "1", "order_id": "999"},
        }

        with patch(
            "app.api.routes.payments.YooKassaClient.get_payment",
            new_callable=AsyncMock,
            return_value=verified,
        ), patch(
            "app.api.routes.payments.ShopService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=_YK_CREDS,
        ):
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/payments/yookassa/webhook",
                    json={
                        "event": "payment.succeeded",
                        "object": {
                            "id": "pay-404",
                            "metadata": {"type": "order", "shop_id": "1", "order_id": "999"},
                        },
                    },
                )

        assert resp.status_code == 200


class TestYooKassaWebhookSubscription:
    """Вебхук ЮKassa — оплата подписки."""

    async def test_subscription_payment_succeeded(
        self, db_session, seed_data, yookassa_enabled, trial_subscription
    ):
        """Успешный платёж подписки — активируется."""
        verified = {
            "id": "pay-sub-1",
            "status": "succeeded",
            "metadata": {
                "type": "subscription",
                "shop_id": "1",
                "plan_id": "10",
            },
        }

        with patch(
            "app.api.routes.payments.YooKassaClient.get_payment",
            new_callable=AsyncMock,
            return_value=verified,
        ), patch(
            "app.services.subscription_payment_service.SubscriptionPaymentService._notify_shop_owner",
            new_callable=AsyncMock,
        ):
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/payments/yookassa/webhook",
                    json={
                        "event": "payment.succeeded",
                        "object": {"id": "pay-sub-1"},
                    },
                )

        assert resp.status_code == 200

        async with db_session() as session:
            sub = await session.get(Subscription, 1)
            assert sub.status == "active"
            assert sub.external_payment_id == "pay-sub-1"

    async def test_subscription_payment_canceled(
        self, db_session, seed_data, yookassa_enabled, trial_subscription
    ):
        """Отмена платежа подписки — подписка не меняется."""
        verified = {
            "id": "pay-sub-cancel",
            "status": "succeeded",
            "metadata": {
                "type": "subscription",
                "shop_id": "1",
                "plan_id": "10",
            },
        }

        with patch(
            "app.api.routes.payments.YooKassaClient.get_payment",
            new_callable=AsyncMock,
            return_value=verified,
        ):
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/payments/yookassa/webhook",
                    json={
                        "event": "payment.canceled",
                        "object": {"id": "pay-sub-cancel"},
                    },
                )

        assert resp.status_code == 200

        async with db_session() as session:
            sub = await session.get(Subscription, 1)
            assert sub.status == "trial"


class TestYooKassaWebhookNegative:
    """Негативные и edge-case сценарии вебхука."""

    async def test_yookassa_not_configured(self, db_session, seed_data, monkeypatch):
        """ЮKassa не настроена — 403."""
        monkeypatch.setattr(settings, "yookassa_shop_id", None)
        monkeypatch.setattr(settings, "yookassa_secret_key", None)

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/payments/yookassa/webhook",
                json={"event": "payment.succeeded", "object": {"id": "x"}},
            )

        assert resp.status_code == 403
        assert resp.json()["error"] == "yookassa_not_configured"

    async def test_missing_payment_id(self, db_session, seed_data, yookassa_enabled):
        """Нет payment_id в payload — 400."""
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/payments/yookassa/webhook",
                json={"event": "payment.succeeded", "object": {}},
            )

        assert resp.status_code == 400
        assert resp.json()["error"] == "missing_payment_id"

    async def test_verification_failed(
        self, db_session, seed_data, yookassa_enabled
    ):
        """YooKassaClient.get_payment вернул None — 400."""
        with patch(
            "app.api.routes.payments.YooKassaClient.get_payment",
            new_callable=AsyncMock,
            return_value=None,
        ):
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/payments/yookassa/webhook",
                    json={
                        "event": "payment.succeeded",
                        "object": {"id": "pay-fail"},
                    },
                )

        assert resp.status_code == 400
        assert resp.json()["error"] == "verification_failed"

    async def test_pending_status(self, db_session, seed_data, yookassa_enabled):
        """Платёж в статусе 'pending' — не обрабатывается, 200 OK."""
        verified = {
            "id": "pay-pending",
            "status": "pending",
            "metadata": {"type": "order", "shop_id": "1", "order_id": "100"},
        }

        with patch(
            "app.api.routes.payments.YooKassaClient.get_payment",
            new_callable=AsyncMock,
            return_value=verified,
        ):
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/payments/yookassa/webhook",
                    json={
                        "event": "payment.waiting_for_capture",
                        "object": {"id": "pay-pending"},
                    },
                )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_metadata_defaults_to_subscription(
        self, db_session, seed_data, yookassa_enabled
    ):
        """Нет metadata.type — маршрутизация в SubscriptionPaymentService."""
        verified = {
            "id": "pay-default",
            "status": "succeeded",
            "metadata": {"shop_id": "1", "plan_id": "10"},
        }

        sub_processed = False

        original = None

        async def fake_process_webhook(data):
            nonlocal sub_processed
            sub_processed = True
            return True

        with patch(
            "app.api.routes.payments.YooKassaClient.get_payment",
            new_callable=AsyncMock,
            return_value=verified,
        ), patch(
            "app.api.routes.payments.SubscriptionPaymentService.process_webhook",
            new=fake_process_webhook,
        ):
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/payments/yookassa/webhook",
                    json={
                        "event": "payment.succeeded",
                        "object": {"id": "pay-default"},
                    },
                )

        assert resp.status_code == 200
        assert sub_processed is True
