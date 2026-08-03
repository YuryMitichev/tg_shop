from unittest.mock import AsyncMock, patch

import pytest

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

    async def test_create_payment_yookassa_fails(self, db_session, seed_data, order_in_db):
        with patch(
            "app.services.order_payment_service.YooKassaClient.create_payment",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

        assert result is None

    async def test_create_payment_metadata_has_type_order(
        self, db_session, seed_data, order_in_db
    ):
        captured = {}

        async def fake_create(amount_rub, description, return_url, metadata):
            captured["metadata"] = metadata
            return {"payment_id": "yk_x", "confirmation_url": "https://yoomoney.ru/x"}

        with patch(
            "app.services.order_payment_service.YooKassaClient.create_payment",
            new=fake_create,
        ):
            await OrderPaymentService.create_payment(shop_id=1, order_id=order_in_db)

        assert captured["metadata"]["type"] == "order"
        assert captured["metadata"]["order_id"] == str(order_in_db)
        assert captured["metadata"]["shop_id"] == "1"


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
