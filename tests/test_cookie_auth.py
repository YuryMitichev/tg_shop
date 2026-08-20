import time
from datetime import datetime, timedelta, timezone
import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import create_app
from app.core.config import settings
from app.models.login_token import LoginToken
from app.services.admin_auth_service import AdminAuthService


@pytest.fixture
def admin_token():
    """Создаёт валидный JWT для тестов."""
    return AdminAuthService._create_token(123456, shop_id=1, is_super_admin=False)


@pytest.fixture
def super_admin_token():
    return AdminAuthService._create_token(999, shop_id=1, is_super_admin=True)


class TestVerifyTokenCookie:
    """Проверка, что /verify-token выставляет httpOnly-cookie."""

    async def test_verify_token_sets_cookie(self, db_session, seed_data):
        token = "test-cookie-token-0123456789abcdef"
        async with db_session() as session:
            session.add(LoginToken(
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                telegram_user_id=123456,
                shop_id=1,
                is_super_admin=False,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
            ))
            await session.commit()

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/auth/verify-token",
                json={"token": token},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        cookies = resp.headers.get_list("set-cookie")
        assert any("admin_token=" in c for c in cookies)
        assert any("httponly" in c.lower() for c in cookies)
        assert any("samesite=lax" in c.lower() for c in cookies)

    async def test_verify_token_invalid(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/auth/verify-token",
                json={"token": "bad-token-that-is-long-enough-for-validation"},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    async def test_verify_token_does_not_return_token_in_json(self, db_session, seed_data):
        token = "test-no-json-token-0123456789abcdef"
        async with db_session() as session:
            session.add(LoginToken(
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                telegram_user_id=123456,
                shop_id=1,
                is_super_admin=False,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
            ))
            await session.commit()

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/auth/verify-token",
                json={"token": token},
            )

        body = resp.json()
        assert body["ok"] is True
        assert "token" not in body


class TestCookieAuth:
    """Проверка, что protected endpoints требуют cookie."""

    async def test_me_without_cookie_unauthorized(self):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/auth/me")

        assert resp.status_code == 401

    async def test_me_with_valid_cookie(self, admin_token, db_session, seed_data):
        with patch(
            "app.services.admin_auth_service.AdminAuthService.verify_token",
            new_callable=AsyncMock,
            return_value={
                "admin_id": 123456,
                "shop_id": 1,
                "is_super_admin": False,
                "role": "owner",
                "authenticated_at": int(datetime.now(timezone.utc).timestamp()),
            },
        ):
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/api/admin/auth/me",
                    cookies={"admin_token": admin_token},
                )

        assert resp.status_code == 200
        assert resp.json()["telegram_user_id"] == 123456

    async def test_me_with_invalid_cookie(self):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/admin/auth/me",
                cookies={"admin_token": "invalid.jwt.token"},
            )

        assert resp.status_code == 401

    async def test_protected_endpoint_without_cookie(self):
        """Любой protected endpoint без cookie → 401."""
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/categories")

        assert resp.status_code == 401


class TestLoginRequestOrigin:
    async def test_rejects_client_supplied_panel_url(self):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/auth/request-login",
                json={
                    "telegram_user_id": 123456,
                    "panel_url": "https://attacker.example",
                },
            )

        assert resp.status_code == 422


class TestLogout:
    """Проверка, что /logout удаляет cookie."""

    async def test_logout_clears_cookie(self):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/admin/auth/logout")

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        cookies = resp.headers.get_list("set-cookie")
        assert any(
            "admin_token=" in c and ("max-age=0" in c.lower() or "expires=" in c.lower())
            for c in cookies
        )
