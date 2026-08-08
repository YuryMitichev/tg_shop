import pytest
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from app.api.main import create_app, init_sentry
from app.core.logging import get_request_id, request_id_var


class TestHealthEndpoint:

    async def test_health_ok(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestRequestIdMiddleware:
    """Middleware генерирует X-Request-Id и возвращает его в ответе."""

    async def test_response_has_request_id(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers
        assert len(resp.headers["x-request-id"]) > 0

    async def test_accepts_custom_request_id(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        custom_id = "my-trace-id-123"
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health", headers={"X-Request-Id": custom_id})
        assert resp.headers["x-request-id"] == custom_id

    async def test_error_response_has_request_id(self):
        app = create_app()

        @app.get("/_test/raise")
        async def _raise():
            raise RuntimeError("boom")

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/_test/raise")

        assert resp.status_code == 500
        assert "x-request-id" in resp.headers
        assert resp.json()["request_id"] == resp.headers["x-request-id"]


class TestGlobalExceptionHandler:
    """Глобальный обработчик ошибок: неперехваченные исключения → 500."""

    async def test_unhandled_exception_returns_500(self):
        app = create_app()

        @app.get("/_test/raise")
        async def _raise():
            raise RuntimeError("boom")

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/_test/raise")

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Внутренняя ошибка сервера"
        assert "request_id" in resp.json()

    async def test_http_exception_still_works(self, db_session, seed_data):
        """HTTPException должен отдавать свой status_code и detail."""
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shop/products/99999", headers={"X-Shop-Id": "1"})
        assert resp.status_code == 404
        assert "detail" in resp.json()


class TestSentryIntegration:
    """Sentry: capture_exception вызывается при неперехваченных исключениях."""

    async def test_sentry_capture_called_on_exception(self):
        app = create_app()

        @app.get("/_test/raise")
        async def _raise():
            raise RuntimeError("sentry-test")

        with patch("app.api.main.sentry_sdk.capture_exception") as mock_capture:
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/_test/raise")

        assert resp.status_code == 500
        mock_capture.assert_called_once()

    def test_init_sentry_noop_without_dsn(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "sentry_dsn", None)
        with patch("app.api.main.sentry_sdk.init") as mock_init:
            init_sentry()
        mock_init.assert_not_called()

    def test_init_sentry_calls_init_with_dsn(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "sentry_dsn", "https://test@sentry.io/123")
        with patch("app.api.main.sentry_sdk.init") as mock_init:
            init_sentry()
        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs["dsn"] == "https://test@sentry.io/123"
