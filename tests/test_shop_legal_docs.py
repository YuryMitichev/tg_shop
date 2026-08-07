"""Тесты per-shop оферты и политики конфиденциальности."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import create_app
from app.models.subscription import Subscription, SubscriptionPlan
from app.services.admin_auth_service import AdminAuthService
from app.services.shop_service import ShopService
from app.utils.crypto import encrypt


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


@pytest.fixture
async def active_subscription(db_session):
    session_maker = db_session
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with session_maker() as session:
        session.add(SubscriptionPlan(
            id=1, name="Тест", price=5000, duration_days=30, is_trial=False,
        ))
        await session.commit()
        session.add(Subscription(
            shop_id=1, plan_id=1, status="active",
            started_at=now, expires_at=now + timedelta(days=25),
        ))
        await session.commit()


# ==========================
# ShopService: update_legal_docs
# ==========================

class TestUpdateLegalDocs:

    async def test_update_offer_and_privacy(self, db_session, seed_data):
        result = await ShopService.update_legal_docs(
            shop_id=1,
            offer_text="Текст оферты",
            privacy_policy_text="Текст политики",
        )
        assert result is not None
        assert result["offer_text"] == "Текст оферты"
        assert result["privacy_policy_text"] == "Текст политики"

    async def test_update_legal_docs_empty_clears(self, db_session, seed_data):
        await ShopService.update_legal_docs(
            shop_id=1,
            offer_text="Оферта",
            privacy_policy_text="Политика",
        )
        result = await ShopService.update_legal_docs(
            shop_id=1,
            offer_text="",
            privacy_policy_text="",
        )
        assert result["offer_text"] is None
        assert result["privacy_policy_text"] is None

    async def test_update_legal_docs_shop_not_found(self, db_session, seed_data):
        result = await ShopService.update_legal_docs(
            shop_id=999,
            offer_text="x",
            privacy_policy_text="y",
        )
        assert result is None

    async def test_shop_to_dict_includes_legal_fields(self, db_session, seed_data):
        await ShopService.update_legal_docs(
            shop_id=1,
            offer_text="Оферта",
            privacy_policy_text="Политика",
        )
        shop = await ShopService.get(1)
        assert shop["offer_text"] == "Оферта"
        assert shop["privacy_policy_text"] == "Политика"


# ==========================
# ShopService: generate_offer_template
# ==========================

class TestGenerateOfferTemplate:

    async def test_generate_with_company_info(self, db_session, seed_data):
        await ShopService.update_company_info(
            shop_id=1,
            company_name="ИП Иванов",
            company_inn="1234567890",
            company_address="г. Москва, ул. Ленина 1",
        )

        template = await ShopService.generate_offer_template(1)

        assert "ИП Иванов" in template["offer_text"]
        assert "1234567890" in template["offer_text"]
        assert "ИП Иванов" in template["privacy_policy_text"]
        assert "1234567890" in template["privacy_policy_text"]

    async def test_generate_without_company_info_uses_shop_name(self, db_session, seed_data):
        template = await ShopService.generate_offer_template(1)

        assert template["offer_text"]
        assert template["privacy_policy_text"]
        assert "Test Shop" in template["offer_text"]

    async def test_generate_shop_not_found(self, db_session, seed_data):
        template = await ShopService.generate_offer_template(999)
        assert template == {"offer_text": "", "privacy_policy_text": ""}


# ==========================
# ShopService: has_accepted_offer / accept_offer
# ==========================

class TestShopOfferConsent:

    async def test_has_accepted_false_by_default(self, db_session, seed_data):
        result = await ShopService.has_accepted_offer(1, 111)
        assert result is False

    async def test_accept_offer(self, db_session, seed_data):
        record = await ShopService.accept_offer(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван",
            username="ivan",
        )
        assert record.shop_id == 1
        assert record.telegram_user_id == 111
        assert record.full_name == "Иван"

    async def test_has_accepted_true_after_accept(self, db_session, seed_data):
        await ShopService.accept_offer(1, 111, "Иван", "ivan")
        result = await ShopService.has_accepted_offer(1, 111)
        assert result is True

    async def test_accept_offer_idempotent(self, db_session, seed_data):
        r1 = await ShopService.accept_offer(1, 111, "Иван", "ivan")
        r2 = await ShopService.accept_offer(1, 111, "Пётр", "petr")
        assert r1.id == r2.id
        assert r2.full_name == "Иван"

    async def test_accept_offer_is_per_shop(self, db_session, seed_data):
        await ShopService.accept_offer(1, 111, "Иван", "ivan")
        assert await ShopService.has_accepted_offer(1, 111) is True

        await ShopService.create("Магазин 2", "tok:second", 222)
        assert await ShopService.has_accepted_offer(2, 111) is False


# ==========================
# Admin API: GET/PUT /settings/legal, POST /settings/legal/generate
# ==========================

class TestAdminLegalDocs:

    async def test_get_legal_docs_empty(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/settings/legal", cookies=admin_cookie)

        assert resp.status_code == 200
        data = resp.json()
        assert data["offer_text"] is None
        assert data["privacy_policy_text"] is None

    async def test_update_legal_docs(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/legal",
                cookies=admin_cookie,
                json={
                    "offer_text": "Моя оферта",
                    "privacy_policy_text": "Моя политика",
                },
            )

        assert resp.status_code == 200

        shop = await ShopService.get(1)
        assert shop["offer_text"] == "Моя оферта"
        assert shop["privacy_policy_text"] == "Моя политика"

    async def test_generate_legal_template(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/settings/legal/generate",
                cookies=admin_cookie,
                json={},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["offer_text"]
        assert data["privacy_policy_text"]
        assert "Test Shop" in data["offer_text"]

    async def test_update_legal_docs_requires_auth(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/legal",
                json={"offer_text": "x"},
            )

        assert resp.status_code == 401


# ==========================
# Public routes: GET /legal/{shop_id}/offer and /privacy
# ==========================

class TestPublicLegalRoutes:

    async def test_get_offer_with_text(self, db_session, seed_data):
        await ShopService.update_legal_docs(
            shop_id=1, offer_text="Публичная оферта", privacy_policy_text=None
        )

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shop/legal/1/offer")

        assert resp.status_code == 200
        assert resp.json()["text"] == "Публичная оферта"

    async def test_get_offer_without_text_404(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shop/legal/1/offer")

        assert resp.status_code == 404

    async def test_get_privacy_with_text(self, db_session, seed_data):
        await ShopService.update_legal_docs(
            shop_id=1, offer_text=None, privacy_policy_text="Политика"
        )

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shop/legal/1/privacy")

        assert resp.status_code == 200
        assert resp.json()["text"] == "Политика"

    async def test_get_privacy_without_text_404(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shop/legal/1/privacy")

        assert resp.status_code == 404

    async def test_legal_routes_no_auth_required(self, db_session, seed_data):
        await ShopService.update_legal_docs(
            shop_id=1, offer_text="Оферта", privacy_policy_text="Политика"
        )

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp_offer = await client.get("/api/shop/legal/1/offer")
            resp_privacy = await client.get("/api/shop/legal/1/privacy")

        assert resp_offer.status_code == 200
        assert resp_privacy.status_code == 200

    async def test_legal_routes_shop_not_found(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shop/legal/999/offer")

        assert resp.status_code == 404


# ==========================
# Bot: checkout consent gate
# ==========================

def _make_callback_query(data, user_id=111):
    from aiogram.types import CallbackQuery, Chat, Message, User
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = User(id=user_id, is_bot=False, first_name="Test")
    cb.message = MagicMock(spec=Message)
    cb.message.chat = Chat(id=1, type="private")
    cb.message.message_id = 1
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.bot = MagicMock()
    cb.answer = AsyncMock()
    return cb


class TestCheckoutConsentGate:

    async def test_checkout_shows_consent_when_offer_set(self, db_session, seed_data):
        from app.bot.handlers.cart import setup_router
        from aiogram.fsm.context import FSMContext
        from app.services.cart_service import CartService

        await ShopService.update_legal_docs(
            shop_id=1, offer_text="Оферта магазина", privacy_policy_text=None
        )
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)

        router = setup_router()
        checkout_handler = router.callback_query.handlers[4].callback

        state = MagicMock(spec=FSMContext)
        cb = _make_callback_query(data="checkout", user_id=111)

        with patch("app.bot.handlers.cart.settings") as mock_settings:
            mock_settings.webapp_enabled = True
            mock_settings.webapp_url = "https://app.test"
            await checkout_handler(cb, state)

        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args.args[0]
        assert "оферты" in text.lower() or "оферта" in text.lower()

    async def test_checkout_no_consent_when_no_offer_text(self, db_session, seed_data):
        from app.bot.handlers.cart import setup_router
        from aiogram.fsm.context import FSMContext
        from app.services.cart_service import CartService

        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)

        router = setup_router()
        checkout_handler = router.callback_query.handlers[4].callback

        state = MagicMock(spec=FSMContext)
        cb = _make_callback_query(data="checkout", user_id=111)

        with patch("app.bot.handlers.cart.settings") as mock_settings:
            mock_settings.webapp_enabled = True
            mock_settings.webapp_url = "https://app.test"
            await checkout_handler(cb, state)

        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args.args[0]
        assert "оформить заказ" in text.lower() or "отлично" in text.lower()

    async def test_checkout_no_consent_after_acceptance(self, db_session, seed_data):
        from app.bot.handlers.cart import setup_router
        from aiogram.fsm.context import FSMContext
        from app.services.cart_service import CartService

        await ShopService.update_legal_docs(
            shop_id=1, offer_text="Оферта магазина", privacy_policy_text=None
        )
        await ShopService.accept_offer(1, 111, "Test", "test")
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)

        router = setup_router()
        checkout_handler = router.callback_query.handlers[4].callback

        state = MagicMock(spec=FSMContext)
        cb = _make_callback_query(data="checkout", user_id=111)

        with patch("app.bot.handlers.cart.settings") as mock_settings:
            mock_settings.webapp_enabled = True
            mock_settings.webapp_url = "https://app.test"
            await checkout_handler(cb, state)

        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args.args[0]
        assert "оформить заказ" in text.lower() or "отлично" in text.lower()

    async def test_accept_shop_offer_callback(self, db_session, seed_data):
        from app.bot.handlers.cart import setup_router

        await ShopService.update_legal_docs(
            shop_id=1, offer_text="Оферта", privacy_policy_text=None
        )

        router = setup_router()
        accept_handler = router.callback_query.handlers[6].callback

        cb = _make_callback_query(data="accept_shop_offer", user_id=111)

        with patch("app.bot.handlers.cart.settings") as mock_settings:
            mock_settings.webapp_enabled = True
            mock_settings.webapp_url = "https://app.test"
            await accept_handler(cb)

        accepted = await ShopService.has_accepted_offer(1, 111)
        assert accepted is True
