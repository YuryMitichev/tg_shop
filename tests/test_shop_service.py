import pytest

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
