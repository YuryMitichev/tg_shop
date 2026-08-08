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

    async def test_checkout_shows_pd_consent_when_no_offer_text(self, db_session, seed_data):
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
        assert "согласие" in text.lower()

    async def test_checkout_shows_pd_consent_after_offer_acceptance(self, db_session, seed_data):
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
        assert "согласие" in text.lower()

    async def test_accept_shop_offer_callback(self, db_session, seed_data):
        from app.bot.handlers.cart import setup_router

        await ShopService.update_legal_docs(
            shop_id=1, offer_text="Оферта", privacy_policy_text=None
        )

        router = setup_router()
        accept_handler = router.callback_query.handlers[8].callback

        cb = _make_callback_query(data="accept_shop_offer", user_id=111)

        with patch("app.bot.handlers.cart.settings") as mock_settings:
            mock_settings.webapp_enabled = True
            mock_settings.webapp_url = "https://app.test"
            await accept_handler(cb)

        accepted = await ShopService.has_accepted_offer(1, 111)
        assert accepted is True


# ==========================
# Admin API: GET /settings/legal-documents, PUT seller addendum
# ==========================

class TestAdminLegalDocuments:

    async def test_get_all_legal_documents(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/admin/settings/legal-documents", cookies=admin_cookie
            )

        assert resp.status_code == 200
        docs = resp.json()
        assert len(docs) == 4
        types = [d["document_type"] for d in docs]
        assert "privacy_policy" in types
        assert "customer_consent" in types
        assert "order_terms" in types
        assert "data_processing_mandate" in types

    async def test_legal_documents_have_system_template(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/admin/settings/legal-documents", cookies=admin_cookie
            )

        docs = resp.json()
        for doc in docs:
            assert doc["system_template"]
            assert doc["title"]
            assert "text" in doc

    async def test_legal_documents_no_addendum_by_default(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/admin/settings/legal-documents", cookies=admin_cookie
            )

        docs = resp.json()
        for doc in docs:
            assert doc["seller_addendum"] is None

    async def test_data_processing_mandate_is_read_only(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/admin/settings/legal-documents", cookies=admin_cookie
            )

        docs = resp.json()
        mandate = next(d for d in docs if d["document_type"] == "data_processing_mandate")
        assert mandate["is_read_only"] is True
        for doc in docs:
            if doc["document_type"] != "data_processing_mandate":
                assert doc["is_read_only"] is False

    async def test_update_seller_addendum(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/legal-documents/privacy_policy",
                cookies=admin_cookie,
                json={"seller_addendum": "Дополнительные условия"},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        from app.services.legal_document_service import LegalDocumentService
        addendum = await LegalDocumentService.get_seller_addendum(1, "privacy_policy")
        assert addendum == "Дополнительные условия"

    async def test_update_seller_addendum_clear(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        from app.services.legal_document_service import LegalDocumentService
        await LegalDocumentService.update_seller_addendum(1, "order_terms", "Текст")

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/legal-documents/order_terms",
                cookies=admin_cookie,
                json={"seller_addendum": None},
            )

        assert resp.status_code == 200
        addendum = await LegalDocumentService.get_seller_addendum(1, "order_terms")
        assert addendum is None

    async def test_update_addendum_mandate_forbidden(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/legal-documents/data_processing_mandate",
                cookies=admin_cookie,
                json={"seller_addendum": "x"},
            )

        assert resp.status_code == 403

    async def test_update_addendum_invalid_type(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/legal-documents/nonexistent",
                cookies=admin_cookie,
                json={"seller_addendum": "x"},
            )

        assert resp.status_code == 400

    async def test_legal_documents_require_auth(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/settings/legal-documents")

        assert resp.status_code == 401


# ==========================
# Admin API: company info with legal_type
# ==========================

class TestCompanyInfoLegalType:

    async def test_get_company_info_includes_legal_type(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/settings/company", cookies=admin_cookie)

        assert resp.status_code == 200
        assert resp.json()["legal_type"] == "individual"

    async def test_update_legal_type(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/company",
                cookies=admin_cookie,
                json={"legal_type": "ooo", "company_name": "ООО Ромашка"},
            )

        assert resp.status_code == 200
        shop = await ShopService.get(1)
        assert shop["legal_type"] == "ooo"
        assert shop["company_name"] == "ООО Ромашка"

    async def test_legal_type_reflected_in_documents(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.put(
                "/api/admin/settings/company",
                cookies=admin_cookie,
                json={"legal_type": "ip", "company_name": "ИП Сидоров"},
            )
            resp = await client.get(
                "/api/admin/settings/legal-documents", cookies=admin_cookie
            )

        docs = resp.json()
        mandate = next(d for d in docs if d["document_type"] == "data_processing_mandate")
        assert "Индивидуальный предприниматель" in mandate["system_template"]
        assert "ИП Сидоров" in mandate["system_template"]


# ==========================
# Admin API: Roskomnadzor
# ==========================

class TestRoskomnadzor:

    async def test_get_roskomnadzor_info(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/admin/settings/roskomnadzor", cookies=admin_cookie
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["legal_type"] == "individual"
        assert "info" in data
        assert "official_url" in data
        assert "rkn.gov.ru" in data["official_url"]

    async def test_get_roskomnadzor_draft(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        await ShopService.update_company_info(
            shop_id=1,
            company_name="ООО Тест",
            company_inn="0987654321",
            company_address="г. Москва",
            legal_type="ooo",
        )

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/admin/settings/roskomnadzor/draft", cookies=admin_cookie
            )

        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")
        body = resp.text
        assert "УВЕДОМЛЕНИЕ" in body
        assert "ООО Тест" in body
        assert "0987654321" in body
        assert "Общество с ограниченной ответственностью" in body
        assert "attachment" in resp.headers.get("content-disposition", "")

    async def test_roskomnadzor_requires_auth(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/settings/roskomnadzor")

        assert resp.status_code == 401

    async def test_roskomnadzor_draft_requires_auth(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/settings/roskomnadzor/draft")

        assert resp.status_code == 401


# ==========================
# Public routes: GET /legal/{shop_id}/documents
# ==========================

class TestPublicLegalDocumentRoutes:

    async def test_list_documents(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shop/legal/1/documents")

        assert resp.status_code == 200
        docs = resp.json()
        assert len(docs) == 4
        titles = {d["title"] for d in docs}
        assert any("Политика" in t for t in titles)
        assert any("Согласие" in t for t in titles)

    async def test_list_documents_no_auth_required(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shop/legal/1/documents")

        assert resp.status_code == 200

    async def test_list_documents_shop_not_found(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shop/legal/999/documents")

        assert resp.status_code == 404

    async def test_get_single_document(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/shop/legal/1/documents/privacy_policy"
            )

        assert resp.status_code == 200
        doc = resp.json()
        assert doc["document_type"] == "privacy_policy"
        assert doc["system_template"]
        assert "text" in doc

    async def test_get_document_with_addendum(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.put(
                "/api/admin/settings/legal-documents/order_terms",
                cookies=admin_cookie,
                json={"seller_addendum": "Особые условия доставки"},
            )
            resp = await client.get(
                "/api/shop/legal/1/documents/order_terms"
            )

        assert resp.status_code == 200
        doc = resp.json()
        assert "Особые условия доставки" in doc["text"]
        assert doc["seller_addendum"] == "Особые условия доставки"

    async def test_get_mandate_document(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/shop/legal/1/documents/data_processing_mandate"
            )

        assert resp.status_code == 200
        doc = resp.json()
        assert doc["is_read_only"] is True
        assert "ПОРУЧЕНИЕ" in doc["system_template"]

    async def test_get_invalid_document_type(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/shop/legal/1/documents/nonexistent"
            )

        assert resp.status_code == 404

    async def test_get_document_shop_not_found(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/shop/legal/999/documents/privacy_policy"
            )

        assert resp.status_code == 404


# ==========================
# LegalDocumentService unit tests
# ==========================

class TestLegalDocumentService:

    async def test_render_document_nonexistent_shop(self, db_session, seed_data):
        from app.services.legal_document_service import LegalDocumentService
        result = await LegalDocumentService.render_document(999, "privacy_policy")
        assert result is None

    async def test_get_all_documents_nonexistent_shop(self, db_session, seed_data):
        from app.services.legal_document_service import LegalDocumentService
        result = await LegalDocumentService.get_all_documents(999)
        assert result is None

    async def test_get_customer_consent_text(self, db_session, seed_data):
        from app.services.legal_document_service import LegalDocumentService
        text = await LegalDocumentService.get_customer_consent_text(1)
        assert text is not None
        assert "СОГЛАСИЕ" in text

    async def test_get_customer_consent_text_nonexistent_shop(self, db_session, seed_data):
        from app.services.legal_document_service import LegalDocumentService
        text = await LegalDocumentService.get_customer_consent_text(999)
        assert text is None

    async def test_update_and_get_addendum_roundtrip(self, db_session, seed_data):
        from app.services.legal_document_service import LegalDocumentService
        await LegalDocumentService.update_seller_addendum(1, "privacy_policy", "Текст А")
        result = await LegalDocumentService.get_seller_addendum(1, "privacy_policy")
        assert result == "Текст А"

        await LegalDocumentService.update_seller_addendum(1, "privacy_policy", None)
        result = await LegalDocumentService.get_seller_addendum(1, "privacy_policy")
        assert result is None

    async def test_roskomnadzor_draft_contains_required_fields(self, db_session, seed_data):
        from app.services.legal_document_service import LegalDocumentService
        await ShopService.update_company_info(
            shop_id=1,
            company_name="ИП Иванов",
            company_inn="1234567890",
            company_address="г. Москва, ул. Пушкина",
            legal_type="ip",
        )
        shop = await ShopService.get(1)
        draft = LegalDocumentService.get_roskomnadzor_draft(shop)
        assert "Индивидуальный предприниматель" in draft
        assert "ИП Иванов" in draft
        assert "1234567890" in draft
        assert "152-ФЗ" in draft
        assert "pd.rkn.gov.ru" in draft
