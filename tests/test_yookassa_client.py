import base64
from unittest.mock import patch

from app.services.yookassa_client import YooKassaClient


class MockResponse:
    def __init__(self, status, json_data):
        self.status = status
        self._json_data = json_data

    async def json(self):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockSession:
    def __init__(self, response):
        self._response = response

    def post(self, *args, **kwargs):
        return self._response

    def get(self, *args, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class TestAuthHeader:

    def test_auth_header_format(self):
        from app.core.config import settings

        with patch.object(settings, "yookassa_shop_id", "12345"):
            with patch.object(settings, "yookassa_secret_key", "secret_xxx"):
                header = YooKassaClient._auth_header()

                assert header.startswith("Basic ")
                encoded = header[6:]
                decoded = base64.b64decode(encoded).decode()
                assert decoded == "12345:secret_xxx"


class TestCreatePayment:

    async def test_create_payment_success(self):
        mock_response = MockResponse(200, {
            "id": "yk_payment_id",
            "status": "pending",
            "confirmation": {
                "confirmation_url": "https://yoomoney.ru/checkout?id=123",
            },
        })

        with patch(
            "app.services.yookassa_client.aiohttp.ClientSession",
            return_value=MockSession(mock_response),
        ):
            result = await YooKassaClient.create_payment(
                amount_rub=990,
                description="Test",
                return_url="https://example.com",
                metadata={"shop_id": "1", "plan_id": "2"},
            )

        assert result is not None
        assert result["payment_id"] == "yk_payment_id"
        assert result["confirmation_url"] == "https://yoomoney.ru/checkout?id=123"

    async def test_create_payment_api_error(self):
        mock_response = MockResponse(400, {"error": "bad request"})

        with patch(
            "app.services.yookassa_client.aiohttp.ClientSession",
            return_value=MockSession(mock_response),
        ):
            result = await YooKassaClient.create_payment(
                amount_rub=990,
                description="Test",
                return_url="https://example.com",
                metadata={},
            )

        assert result is None


class TestGetPayment:

    async def test_get_payment_success(self):
        mock_response = MockResponse(200, {
            "id": "yk_payment_id",
            "status": "succeeded",
        })

        with patch(
            "app.services.yookassa_client.aiohttp.ClientSession",
            return_value=MockSession(mock_response),
        ):
            result = await YooKassaClient.get_payment("yk_payment_id")

        assert result is not None
        assert result["status"] == "succeeded"

    async def test_get_payment_not_found(self):
        mock_response = MockResponse(404, {"error": "not found"})

        with patch(
            "app.services.yookassa_client.aiohttp.ClientSession",
            return_value=MockSession(mock_response),
        ):
            result = await YooKassaClient.get_payment("yk_invalid")

        assert result is None
