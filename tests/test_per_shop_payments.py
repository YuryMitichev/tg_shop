"""Тесты per-shop платёжных настроек: ShopService, admin API, routes."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import create_app
from app.services.admin_auth_service import AdminAuthService
from app.services.shop_service import ShopService, _mask_secret_key
from app.utils.crypto import encrypt


_YK_SHOP_ID = "123456"
_YK_SECRET = "live_abcdef1234567890"

_ADMIN_DICT = {"admin_id": 123456, "shop_id": 1, "is_super_admin": False}


@pytest.fixture
def admin_cookie():
    """Создаёт валидный JWT для cookie."""
    token = AdminAuthService._create_token(123456, shop_id=1, is_super_admin=False)
    return {"admin_token": token}


@pytest.fixture
def mock_admin_auth():
    """Мокает verify_token — обходит проверку БД."""
    with patch(
        "app.api.admin_auth.AdminAuthService.verify_token",
        new_callable=AsyncMock,
        return_value=_ADMIN_DICT,
    ):
        yield


class TestShopServicePaymentSettings:
    """Тесты ShopService.update_payment_settings + get_yookassa_credentials."""

    async def test_update_payment_settings(self, db_session, seed_data):
        result = await ShopService.update_payment_settings(
            shop_id=1,
            payment_card_number="4111 1111 1111 1111",
            payment_recipient_name="Иван И.",
            yookassa_shop_id=_YK_SHOP_ID,
            yookassa_secret_key=_YK_SECRET,
            yookassa_enabled=True,
            manual_payment_enabled=True,
        )

        assert result is not None
        assert result["payment_card_number"] == "4111 1111 1111 1111"
        assert result["payment_recipient_name"] == "Иван И."
        assert result["yookassa_shop_id"] == _YK_SHOP_ID
        assert result["yookassa_enabled"] is True
        assert result["manual_payment_enabled"] is True
        assert _YK_SECRET[-4:] in result["yookassa_secret_key_masked"]

    async def test_update_payment_settings_partial(self, db_session, seed_data):
        await ShopService.update_payment_settings(
            shop_id=1,
            payment_card_number="4111",
        )

        shop = await ShopService.get(1)
        assert shop["payment_card_number"] == "4111"
        assert shop["yookassa_enabled"] is False

    async def test_update_payment_settings_shop_not_found(self, db_session, seed_data):
        result = await ShopService.update_payment_settings(
            shop_id=999,
            payment_card_number="x",
        )
        assert result is None

    async def test_get_yookassa_credentials(self, db_session, seed_data):
        await ShopService.update_payment_settings(
            shop_id=1,
            yookassa_shop_id=_YK_SHOP_ID,
            yookassa_secret_key=_YK_SECRET,
        )

        creds = await ShopService.get_yookassa_credentials(1)
        assert creds is not None
        assert creds[0] == _YK_SHOP_ID
        assert creds[1] == _YK_SECRET

    async def test_get_yookassa_credentials_not_configured(self, db_session, seed_data):
        creds = await ShopService.get_yookassa_credentials(1)
        assert creds is None

    async def test_get_yookassa_credentials_shop_not_found(self, db_session, seed_data):
        creds = await ShopService.get_yookassa_credentials(999)
        assert creds is None

    async def test_update_yookassa_secret_key_none_preserves_existing(
        self, db_session, seed_data
    ):
        await ShopService.update_payment_settings(
            shop_id=1,
            yookassa_shop_id=_YK_SHOP_ID,
            yookassa_secret_key=_YK_SECRET,
        )

        await ShopService.update_payment_settings(
            shop_id=1,
            yookassa_enabled=True,
        )

        creds = await ShopService.get_yookassa_credentials(1)
        assert creds is not None
        assert creds[1] == _YK_SECRET


class TestMaskSecretKey:

    def test_mask_normal_key(self):
        assert _mask_secret_key("live_abcdef123456") == "****3456"

    def test_mask_short_key(self):
        assert _mask_secret_key("ab") == "****"

    def test_mask_none(self):
        assert _mask_secret_key(None) is None

    def test_mask_empty(self):
        assert _mask_secret_key("") is None


class TestPaymentMethodsRoute:
    """Тесты GET /payment-methods — per-shop настройки."""

    async def test_default_manual_only(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shop/payment-methods", headers={"X-Shop-Id": "1"})

        assert resp.status_code == 200
        methods = resp.json()
        assert len(methods) == 1
        assert methods[0]["id"] == "manual"

    async def test_yookassa_enabled(self, db_session, seed_data):
        await ShopService.update_payment_settings(
            shop_id=1,
            yookassa_shop_id=_YK_SHOP_ID,
            yookassa_secret_key=_YK_SECRET,
            yookassa_enabled=True,
            manual_payment_enabled=False,
        )

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shop/payment-methods", headers={"X-Shop-Id": "1"})

        assert resp.status_code == 200
        methods = resp.json()
        assert len(methods) == 1
        assert methods[0]["id"] == "yookassa"

    async def test_both_enabled(self, db_session, seed_data):
        await ShopService.update_payment_settings(
            shop_id=1,
            payment_card_number="4111 1111",
            payment_recipient_name="Иван",
            yookassa_shop_id=_YK_SHOP_ID,
            yookassa_secret_key=_YK_SECRET,
            yookassa_enabled=True,
            manual_payment_enabled=True,
        )

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shop/payment-methods", headers={"X-Shop-Id": "1"})

        assert resp.status_code == 200
        methods = resp.json()
        assert len(methods) == 2
        ids = [m["id"] for m in methods]
        assert "yookassa" in ids
        assert "manual" in ids

        manual = next(m for m in methods if m["id"] == "manual")
        assert manual["card_number"] == "4111 1111"
        assert manual["recipient"] == "Иван"

    async def test_manual_card_fallback_to_global(self, db_session, seed_data):
        from app.core.config import settings
        from unittest.mock import patch as _patch

        with _patch.object(settings, "payment_card_number", "GLOBAL_CARD"):
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/shop/payment-methods", headers={"X-Shop-Id": "1"})

        assert resp.status_code == 200
        methods = resp.json()
        manual = next(m for m in methods if m["id"] == "manual")
        assert manual["card_number"] == "GLOBAL_CARD"


class TestAdminPaymentSettings:
    """Тесты admin API: GET/PUT /settings/payments."""

    async def test_get_payment_settings(
        self, db_session, seed_data, admin_cookie, mock_admin_auth
    ):
        await ShopService.update_payment_settings(
            shop_id=1,
            payment_card_number="4111",
            yookassa_shop_id=_YK_SHOP_ID,
            yookassa_secret_key=_YK_SECRET,
            yookassa_enabled=True,
        )

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/admin/settings/payments",
                cookies=admin_cookie,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["payment_card_number"] == "4111"
        assert data["yookassa_shop_id"] == _YK_SHOP_ID
        assert data["yookassa_enabled"] is True
        assert data["manual_payment_enabled"] is True
        assert _YK_SECRET[-4:] in data["yookassa_secret_key_masked"]

    async def test_update_payment_settings(
        self, db_session, seed_data, admin_cookie, mock_admin_auth
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/payments",
                cookies=admin_cookie,
                json={
                    "payment_card_number": "4222 2222",
                    "payment_recipient_name": "Пётр",
                    "yookassa_shop_id": _YK_SHOP_ID,
                    "yookassa_secret_key": _YK_SECRET,
                    "yookassa_enabled": True,
                    "manual_payment_enabled": False,
                },
            )

        assert resp.status_code == 200

        shop = await ShopService.get(1)
        assert shop["payment_card_number"] == "4222 2222"
        assert shop["yookassa_enabled"] is True
        assert shop["manual_payment_enabled"] is False

    async def test_update_payment_settings_no_secret_preserves(
        self, db_session, seed_data, admin_cookie, mock_admin_auth
    ):
        await ShopService.update_payment_settings(
            shop_id=1,
            yookassa_shop_id=_YK_SHOP_ID,
            yookassa_secret_key=_YK_SECRET,
        )

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/payments",
                cookies=admin_cookie,
                json={
                    "yookassa_enabled": True,
                },
            )

        assert resp.status_code == 200

        creds = await ShopService.get_yookassa_credentials(1)
        assert creds is not None
        assert creds[1] == _YK_SECRET
