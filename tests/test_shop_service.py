import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import create_app
from app.services.shop_service import ShopService


class TestShopService:

    async def test_get_all_default(self, db_session, seed_data):
        shops = await ShopService.get_all()

        assert len(shops) == 1
        assert shops[0]["id"] == 1
        assert shops[0]["name"] == "Test Shop"
        assert shops[0]["is_active"] is True
        assert "bot_token" not in shops[0]
        assert "bot_token_masked" in shops[0]

    async def test_create_shop(self, db_session, seed_data):
        shop = await ShopService.create(
            name="Магазин 2",
            bot_token="123456:ABC",
            owner_telegram_id=999,
        )

        assert shop["id"] == 2
        assert shop["name"] == "Магазин 2"
        assert "bot_token" not in shop
        assert shop["owner_telegram_id"] == 999
        assert shop["is_active"] is True

    async def test_get_shop(self, db_session, seed_data):
        shop = await ShopService.get(1)

        assert shop is not None
        assert shop["name"] == "Test Shop"

    async def test_get_shop_not_found(self, db_session, seed_data):
        shop = await ShopService.get(999)

        assert shop is None

    async def test_update_shop_name(self, db_session, seed_data):
        shop = await ShopService.update(1, name="Новое название")

        assert shop["name"] == "Новое название"

    async def test_get_bot_token_decrypts(self, db_session, seed_data):
        token = await ShopService.get_bot_token(1)
        assert token == "test:token"

    async def test_get_bot_token_caches(self, db_session, seed_data):
        token1 = await ShopService.get_bot_token(1)
        ShopService.invalidate_token_cache()
        token2 = await ShopService.get_bot_token(1)
        assert token1 == token2 == "test:token"

    async def test_update_shop_token_invalidates_cache(self, db_session, seed_data):
        await ShopService.get_bot_token(1)
        await ShopService.update(1, bot_token="new:token:123")
        token = await ShopService.get_bot_token(1)
        assert token == "new:token:123"

    async def test_update_shop_activate_deactivate(self, db_session, seed_data):
        shop = await ShopService.update(1, is_active=False)
        assert shop["is_active"] is False

        shop = await ShopService.update(1, is_active=True)
        assert shop["is_active"] is True

    async def test_update_shop_not_found(self, db_session, seed_data):
        shop = await ShopService.update(999, name="Нет")
        assert shop is None

    async def test_delete_shop(self, db_session, seed_data):
        created = await ShopService.create("Временный", "temp:token", 111)
        shop_id = created["id"]

        ok = await ShopService.delete(shop_id)
        assert ok is True

        shop = await ShopService.get(shop_id)
        assert shop is None

    async def test_cannot_delete_default_shop(self, db_session, seed_data):
        ok = await ShopService.delete(1)
        assert ok is False

    async def test_delete_shop_not_found(self, db_session, seed_data):
        ok = await ShopService.delete(999)
        assert ok is False

    async def test_delete_shop_cascades_all_related(self, db_session, seed_data):
        """Удаление магазина очищает все 17 связанных таблиц."""
        from datetime import datetime, timezone
        from app.models import (
            Category, Product, ProductVariant, ProductPhoto,
            Order, OrderItem, CartItem, Review, PromoCode,
            UserProfile, AdminUser, CommunicationLog, SystemMessage,
            LoginToken, Broadcast, UserOffer, ShopOfferAcceptance,
        )
        from app.models.subscription import Subscription, SubscriptionPlan

        session_maker = db_session

        await ShopService.create("Магазин 2", "tok:cascade", 555)

        async with session_maker() as session:
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            session.add(SubscriptionPlan(id=10, name="План", price=100, duration_days=7))
            await session.flush()

            session.add_all([
                Category(id=100, shop_id=2, name="Cat2"),
                Product(id=100, shop_id=2, category_id=100, name="P2", description="d"),
                ProductVariant(id=100, shop_id=2, product_id=100, volume="v", price=10, stock=1),
                ProductPhoto(id=100, shop_id=2, product_id=100, file_id="fid"),
                Order(id=100, shop_id=2, telegram_user_id=55, full_name="N", phone="P", address="A", total_amount=10),
                OrderItem(id=100, shop_id=2, order_id=100, product_name="P", variant_volume="v", price=10, quantity=1),
                CartItem(id=100, shop_id=2, telegram_user_id=55, product_id=100, variant_id=100, quantity=1),
                Review(id=100, shop_id=2, product_id=100, telegram_user_id=55, rating=5),
                PromoCode(id=100, shop_id=2, code="PROMO", discount_value=10),
                UserProfile(id=100, shop_id=2, telegram_user_id=55),
                AdminUser(id=100, shop_id=2, telegram_user_id=55),
                CommunicationLog(id=100, shop_id=2, telegram_user_id=55),
                SystemMessage(id=100, shop_id=2, key="k", content="c"),
                LoginToken(id=100, token="tok-2", shop_id=2, telegram_user_id=55, expires_at=now),
                Broadcast(id=100, shop_id=2, product_id=100, product_name="P", original_price=10, discounted_price=5),
                UserOffer(id=100, shop_id=2, telegram_user_id=55, product_id=100, discount_percent=10),
                ShopOfferAcceptance(shop_id=2, telegram_user_id=55),
                Subscription(shop_id=2, plan_id=10, status="active", started_at=now, expires_at=now),
            ])
            await session.commit()

        ok = await ShopService.delete(2)
        assert ok is True

        async with session_maker() as session:
            from sqlalchemy import select
            for model in [
                Category, Product, ProductVariant, ProductPhoto,
                Order, OrderItem, CartItem, Review, PromoCode,
                UserProfile, AdminUser, CommunicationLog, SystemMessage,
                LoginToken, Broadcast, UserOffer, ShopOfferAcceptance, Subscription,
            ]:
                rows = (await session.execute(
                    select(model).where(model.shop_id == 2)
                )).scalars().all()
                assert len(rows) == 0, f"{model.__tablename__}: остались записи после cascade delete"

            shop1_products = (await session.execute(
                select(Product).where(Product.shop_id == 1)
            )).scalars().all()
            assert len(shop1_products) > 0, "Данные магазина #1 не должны пострадать"

    async def test_get_all_active_only(self, db_session, seed_data):
        await ShopService.create("Активный", "active:token", 111)
        inactive = await ShopService.create("Неактивный", "inactive:token", 222)
        await ShopService.update(inactive["id"], is_active=False)

        all_shops = await ShopService.get_all()
        active = await ShopService.get_all(active_only=True)

        assert len(all_shops) == 3
        assert len(active) == 2

    async def test_get_by_bot_token(self, db_session, seed_data):
        shop = await ShopService.get_by_bot_token("test:token")

        assert shop is not None
        assert shop["id"] == 1

    async def test_get_by_bot_token_not_found(self, db_session, seed_data):
        shop = await ShopService.get_by_bot_token("nonexistent:token")

        assert shop is None

    async def test_create_duplicate_token_rejected(self, db_session, seed_data):
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await ShopService.create(
                name="Дубль",
                bot_token="test:token",
                owner_telegram_id=123,
            )


class TestShopNameEndpoint:
    """Endpoint-тесты для PUT /api/admin/settings/shop."""

    async def test_get_shop_name(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/settings/shop", cookies=admin_cookie)

        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Shop"

    async def test_update_shop_name(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/shop",
                cookies=admin_cookie,
                json={"name": "Новое название"},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        shop = await ShopService.get(1)
        assert shop["name"] == "Новое название"

    async def test_update_shop_name_persists_after_refetch(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            put_resp = await client.put(
                "/api/admin/settings/shop",
                cookies=admin_cookie,
                json={"name": "Обновлённый магазин"},
            )
            assert put_resp.status_code == 200

            get_resp = await client.get("/api/admin/settings/shop", cookies=admin_cookie)

        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Обновлённый магазин"

    async def test_update_shop_name_empty_rejected(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/shop",
                cookies=admin_cookie,
                json={"name": "   "},
            )

        assert resp.status_code == 400

    async def test_update_shop_name_too_long_rejected(
        self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/shop",
                cookies=admin_cookie,
                json={"name": "А" * 101},
            )

        assert resp.status_code == 400

    async def test_update_shop_name_requires_auth(self, db_session, seed_data):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/api/admin/settings/shop",
                json={"name": "Хакер"},
            )

        assert resp.status_code == 401
