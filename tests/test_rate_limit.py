import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import create_app
from app.api.rate_limit import _extract_telegram_user_id, user_or_ip_key


def _make_request(headers: dict | None = None):
    request = MagicMock()
    request.headers = headers or {}
    return request


class TestUserOrIpKeyFunc:
    """Ключевая функция rate limit: пользователь или IP."""

    def test_extracts_user_from_tma_header(self):
        user_data = {"id": 123456, "first_name": "Test"}
        params = {"user": json.dumps(user_data)}
        init_data = "&".join(f"{k}={v}" for k, v in params.items())

        request = _make_request({"authorization": f"tma {init_data}"})
        result = _extract_telegram_user_id(request)
        assert result is not None
        assert "123456" in result

    def test_returns_none_without_auth(self):
        request = _make_request({})
        result = _extract_telegram_user_id(request)
        assert result is None

    def test_returns_none_for_non_tma_auth(self):
        request = _make_request({"authorization": "Bearer some.jwt.token"})
        result = _extract_telegram_user_id(request)
        assert result is None

    def test_returns_none_for_malformed_initdata(self):
        request = _make_request({"authorization": "tma not-valid-json-user"})
        result = _extract_telegram_user_id(request)
        assert result is None

    def test_user_or_ip_fallbacks_to_ip(self):
        request = _make_request({})
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        result = user_or_ip_key(request)
        assert result.startswith("ip:")

    def test_user_or_ip_uses_user_when_present(self):
        user_data = {"id": 999}
        params = {"user": json.dumps(user_data)}
        init_data = "&".join(f"{k}={v}" for k, v in params.items())

        request = _make_request({"authorization": f"tma {init_data}"})
        result = user_or_ip_key(request)
        assert "999" in result


class TestRateLimitOnWebhooks:
    """Rate limit на вебхуках: после N запросов — 429."""

    async def test_yookassa_webhook_rate_limited(self, db_session, seed_data, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "yookassa_shop_id", "test_shop")
        monkeypatch.setattr(settings, "yookassa_secret_key", "test_key")

        with patch(
            "app.api.routes.payments.YooKassaClient.get_payment",
            new_callable=AsyncMock,
            return_value=None,
        ):
            app = create_app()
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                statuses = []
                for i in range(62):
                    resp = await client.post(
                        "/payments/yookassa/webhook",
                        json={"event": "payment.succeeded", "object": {"id": f"pay-{i}"}},
                    )
                    statuses.append(resp.status_code)

        assert 429 in statuses, f"Expected 429 after 60+ requests, got statuses: {set(statuses)}"

    async def test_tinkoff_webhook_rate_limited(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            statuses = []
            for i in range(62):
                resp = await client.post(
                    "/payments/tinkoff/webhook",
                    json={"Status": "AUTHORIZED", "OrderId": str(i)},
                )
                statuses.append(resp.status_code)

        assert 429 in statuses, f"Expected 429 after 60+ requests, got statuses: {set(statuses)}"
