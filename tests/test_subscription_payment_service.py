from unittest.mock import AsyncMock, patch

import pytest

from app.services.subscription_payment_service import SubscriptionPaymentService


@pytest.fixture
async def plans(db_session):
    """Создаёт тестовые тарифы."""
    from app.models.subscription import SubscriptionPlan

    async with db_session() as session:
        session.add_all([
            SubscriptionPlan(
                id=1,
                name="Триал 7 дней",
                price=0,
                duration_days=7,
                is_trial=True,
            ),
            SubscriptionPlan(
                id=2,
                name="Подписка — 1 месяц",
                description="Полный функционал магазина. Стоимость: 5000₽/мес.",
                price=5000,
                duration_days=30,
                is_trial=False,
            ),
        ])
        await session.commit()


class TestProcessWebhook:

    async def test_payment_succeeded_activates_subscription(
        self, db_session, seed_data, plans
    ):
        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_payment_123",
                "status": "succeeded",
                "metadata": {"shop_id": "1", "plan_id": "2"},
            },
        }

        with patch.object(
            SubscriptionPaymentService,
            "_notify_shop_owner",
            new_callable=AsyncMock,
        ):
            result = await SubscriptionPaymentService.process_webhook(data)

        assert result is True

    async def test_payment_canceled(self, db_session, seed_data, plans):
        data = {
            "event": "payment.canceled",
            "object": {
                "id": "yk_payment_456",
                "status": "canceled",
                "metadata": {"shop_id": "1", "plan_id": "2"},
            },
        }

        result = await SubscriptionPaymentService.process_webhook(data)
        assert result is True

    async def test_unknown_event_ignored(self, db_session, seed_data, plans):
        data = {
            "event": "payment.waiting_for_capture",
            "object": {
                "id": "yk_payment_789",
                "metadata": {"shop_id": "1", "plan_id": "2"},
            },
        }

        result = await SubscriptionPaymentService.process_webhook(data)
        assert result is True

    async def test_missing_event(self, db_session, seed_data, plans):
        result = await SubscriptionPaymentService.process_webhook({"foo": "bar"})
        assert result is False

    async def test_missing_metadata(self, db_session, seed_data, plans):
        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_payment_000",
                "status": "succeeded",
                "metadata": {},
            },
        }

        result = await SubscriptionPaymentService.process_webhook(data)
        assert result is False

    async def test_trial_plan_in_metadata_fails(
        self, db_session, seed_data, plans
    ):
        data = {
            "event": "payment.succeeded",
            "object": {
                "id": "yk_trial_attempt",
                "metadata": {"shop_id": "1", "plan_id": "1"},
            },
        }

        with patch.object(
            SubscriptionPaymentService,
            "_notify_shop_owner",
            new_callable=AsyncMock,
        ):
            result = await SubscriptionPaymentService.process_webhook(data)

        assert result is False


class TestCreatePayment:

    async def test_create_payment_success(self, db_session, seed_data, plans):
        mock_response = {
            "payment_id": "yk_test_id",
            "confirmation_url": "https://yoomoney.ru/checkout?id=test",
        }

        with patch(
            "app.services.subscription_payment_service.YooKassaClient.create_payment",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "app.services.subscription_payment_service.PlatformSettingsService.get_yookassa_credentials",
            new_callable=AsyncMock,
            return_value=("test_shop_id", "test_secret_key"),
        ):
            result = await SubscriptionPaymentService.create_payment(
                shop_id=1, plan_id=2
            )

        assert result is not None
        assert result["payment_id"] == "yk_test_id"
        assert "yoomoney.ru" in result["confirmation_url"]

    async def test_create_payment_trial_plan_fails(
        self, db_session, seed_data, plans
    ):
        result = await SubscriptionPaymentService.create_payment(
            shop_id=1, plan_id=1
        )
        assert result is None

    async def test_create_payment_nonexistent_plan(self, db_session, seed_data, plans):
        result = await SubscriptionPaymentService.create_payment(
            shop_id=1, plan_id=999
        )
        assert result is None

    async def test_create_payment_nonexistent_shop(self, db_session, seed_data, plans):
        result = await SubscriptionPaymentService.create_payment(
            shop_id=999, plan_id=2
        )
        assert result is None
