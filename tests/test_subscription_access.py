"""Тесты доступа к админ-панели при просроченной/активной подписке."""
from datetime import datetime, timedelta, timezone

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import create_app
from app.models.subscription import Subscription, SubscriptionPlan
from app.services.admin_auth_service import AdminAuthService

_ADMIN_DICT = {"admin_id": 123456, "shop_id": 1, "is_super_admin": False}


@pytest.fixture
def admin_cookie():
    token = AdminAuthService._create_token(123456, shop_id=1, is_super_admin=False)
    return {"admin_token": token}


@pytest.fixture
def mock_admin_auth():
    with patch(
        "app.api.admin_auth.AdminAuthService.verify_token",
        new_callable=AsyncMock,
        return_value=_ADMIN_DICT,
    ):
        yield


class TestExpiredSubscriptionAccess:
    """Продавец с истёкшей подпиской: заказы/клиенты доступны, остальное — 403."""

    async def test_get_orders_allowed(self, db_session, seed_data, admin_cookie, mock_admin_auth):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/orders", cookies=admin_cookie)

        assert resp.status_code == 200

    async def test_get_order_detail_allowed(self, db_session, seed_data, admin_cookie, mock_admin_auth):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/orders/1", cookies=admin_cookie)

        assert resp.status_code == 200

    async def test_get_crm_users_allowed(self, db_session, seed_data, admin_cookie, mock_admin_auth):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/crm/users", cookies=admin_cookie)

        assert resp.status_code == 200

    async def test_create_product_blocked(self, db_session, seed_data, admin_cookie, mock_admin_auth):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/products",
                cookies=admin_cookie,
                json={
                    "category_id": 1,
                    "name": "Test",
                    "description": "Test desc",
                    "variants": [{"volume": "100 г", "price": 500}],
                },
            )

        assert resp.status_code == 403
        body = resp.json()
        assert body["error"] == "subscription_expired"

    async def test_create_category_blocked(self, db_session, seed_data, admin_cookie, mock_admin_auth):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/categories",
                cookies=admin_cookie,
                json={"name": "New Cat"},
            )

        assert resp.status_code == 403
        assert resp.json()["error"] == "subscription_expired"

    async def test_create_promo_blocked(self, db_session, seed_data, admin_cookie, mock_admin_auth):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/promos",
                cookies=admin_cookie,
                json={"code": "TEST10", "discount_type": "percent", "discount_value": 10},
            )

        assert resp.status_code == 403
        assert resp.json()["error"] == "subscription_expired"

    async def test_stats_blocked(self, db_session, seed_data, admin_cookie, mock_admin_auth):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/stats", cookies=admin_cookie)

        assert resp.status_code == 403

    async def test_settings_blocked(self, db_session, seed_data, admin_cookie, mock_admin_auth):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/settings/delivery", cookies=admin_cookie)

        assert resp.status_code == 403

    async def test_broadcasts_blocked(self, db_session, seed_data, admin_cookie, mock_admin_auth):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/broadcasts", cookies=admin_cookie)

        assert resp.status_code == 403

    async def test_auth_me_returns_subscription_flag(
        self, db_session, seed_data, admin_cookie, mock_admin_auth
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/auth/me", cookies=admin_cookie)

        assert resp.status_code == 200
        assert resp.json()["subscription_active"] is False


class TestActiveSubscriptionAccess:
    """Продавец с активной подпиской: все роуты доступны."""

    async def test_create_product_allowed(self, db_session, seed_data, admin_cookie, mock_admin_auth):
        session_maker = db_session
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with session_maker() as session:
            session.add(SubscriptionPlan(
                id=1, name="Тест", price=690, duration_days=30, is_trial=False,
            ))
            await session.commit()
            session.add(Subscription(
                shop_id=1, plan_id=1, status="active",
                started_at=now, expires_at=now + timedelta(days=25),
            ))
            await session.commit()

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/products",
                cookies=admin_cookie,
                json={
                    "category_id": 1,
                    "name": "Test",
                    "description": "Test desc",
                    "variants": [{"volume": "100 г", "price": 500}],
                },
            )

        assert resp.status_code == 200

    async def test_auth_me_returns_active_flag(
        self, db_session, seed_data, admin_cookie, mock_admin_auth
    ):
        session_maker = db_session
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with session_maker() as session:
            session.add(SubscriptionPlan(
                id=1, name="Тест", price=690, duration_days=30, is_trial=False,
            ))
            await session.commit()
            session.add(Subscription(
                shop_id=1, plan_id=1, status="active",
                started_at=now, expires_at=now + timedelta(days=25),
            ))
            await session.commit()

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/auth/me", cookies=admin_cookie)

        assert resp.status_code == 200
        assert resp.json()["subscription_active"] is True
