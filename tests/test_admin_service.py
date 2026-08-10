from app.services.catalog_admin_service import CatalogAdminService
from app.services.order_admin_service import OrderAdminService
from app.services.stats_service import StatsService
from app.services.admin_user_service import AdminUserService


class TestAdminCategories:

    async def test_get_categories(self, db_session, seed_data):
        categories = await CatalogAdminService.get_categories(1)

        assert len(categories) == 2

    async def test_create_category(self, db_session, seed_data):
        cat_id = await CatalogAdminService.create_category(1, "Аромалампы")

        categories = await CatalogAdminService.get_categories(1)
        assert len(categories) == 3
        assert any(c["name"] == "Аромалампы" for c in categories)

    async def test_create_category_with_emoji(self, db_session, seed_data):
        cat_id = await CatalogAdminService.create_category(1, "Саше", emoji="🌸")

        categories = await CatalogAdminService.get_categories(1)
        cat = next(c for c in categories if c["id"] == cat_id)
        assert cat["emoji"] == "🌸"

    async def test_update_category_emoji(self, db_session, seed_data):
        await CatalogAdminService.update_category_emoji(1, 1, "🔥")

        categories = await CatalogAdminService.get_categories(1)
        cat = next(c for c in categories if c["id"] == 1)
        assert cat["emoji"] == "🔥"

    async def test_update_category_emoji_remove(self, db_session, seed_data):
        await CatalogAdminService.update_category_emoji(1, 1, None)

        categories = await CatalogAdminService.get_categories(1)
        cat = next(c for c in categories if c["id"] == 1)
        assert cat["emoji"] is None

    async def test_rename_category(self, db_session, seed_data):
        await CatalogAdminService.rename_category(1, 1, "Свечи премиум")

        categories = await CatalogAdminService.get_categories(1)
        assert categories[0]["name"] == "Свечи премиум"

    async def test_count_products_in_category(self, db_session, seed_data):
        count = await CatalogAdminService.count_products_in_category(1, 1)

        assert count == 2

    async def test_count_products_empty_category(self, db_session, seed_data):
        cat_id = await CatalogAdminService.create_category(1, "Пустая")

        count = await CatalogAdminService.count_products_in_category(1, cat_id)

        assert count == 0

    async def test_delete_category_empty(self, db_session, seed_data):
        cat_id = await CatalogAdminService.create_category(1, "Пустая")

        ok = await CatalogAdminService.delete_category(1, cat_id)

        assert ok is True
        categories = await CatalogAdminService.get_categories(1)
        assert len(categories) == 2

    async def test_delete_category_with_products(self, db_session, seed_data):
        ok = await CatalogAdminService.delete_category(1, 1)

        assert ok is False
        categories = await CatalogAdminService.get_categories(1)
        assert len(categories) == 2


class TestAdminProducts:

    async def test_get_products_includes_hidden(self, db_session, seed_data):
        result = await CatalogAdminService.get_products(1, 1)

        assert len(result["products"]) == 2
        assert any(p["is_active"] is False for p in result["products"])

    async def test_get_product(self, db_session, seed_data):
        product = await CatalogAdminService.get_product(1, 1)

        assert product is not None
        assert product["name"] == "Кашемир"

    async def test_get_product_not_found(self, db_session, seed_data):
        product = await CatalogAdminService.get_product(1, 999)

        assert product is None

    async def test_create_product(self, db_session, seed_data):
        product_id = await CatalogAdminService.create_product(
            shop_id=1,
            category_id=2,
            name="Новый диффузор",
            description="Описание",
            variants=[
                {"volume": "50 мл", "price": 690},
                {"volume": "100 мл", "price": 1190, "attributes": {}},
            ],
        )

        product = await CatalogAdminService.get_product(1, product_id)
        assert product["name"] == "Новый диффузор"
        assert len(product["variants"]) == 2

    async def test_create_product_with_photos(self, db_session, seed_data):
        product_id = await CatalogAdminService.create_product(
            shop_id=1,
            category_id=1,
            name="С фото",
            description="Описание",
            variants=[{"volume": "100 г", "price": 500}],
            photos=["file_id_1", "file_id_2"],
        )

        product = await CatalogAdminService.get_product(1, product_id)
        assert len(product["photos"]) == 2
        assert product["photos"][0]["file_id"] == "file_id_1"
        assert product["photos"][1]["position"] == 1

    async def test_delete_product(self, db_session, seed_data):
        await CatalogAdminService.delete_product(1, 1)

        product = await CatalogAdminService.get_product(1, 1)
        assert product is None

    async def test_toggle_active(self, db_session, seed_data):
        result = await CatalogAdminService.toggle_active(1, 1)

        assert result is False

        product = await CatalogAdminService.get_product(1, 1)
        assert product["is_active"] is False

    async def test_toggle_active_back(self, db_session, seed_data):
        await CatalogAdminService.toggle_active(1, 1)
        result = await CatalogAdminService.toggle_active(1, 1)

        assert result is True

    async def test_toggle_active_not_found(self, db_session, seed_data):
        result = await CatalogAdminService.toggle_active(1, 999)

        assert result is None

    async def test_update_product_name(self, db_session, seed_data):
        await CatalogAdminService.update_product(1, 1, name="Новое название")

        product = await CatalogAdminService.get_product(1, 1)
        assert product["name"] == "Новое название"
        assert product["description"] == "Теплый аромат"

    async def test_update_product_description(self, db_session, seed_data):
        await CatalogAdminService.update_product(1, 1, description="Новое описание")

        product = await CatalogAdminService.get_product(1, 1)
        assert product["description"] == "Новое описание"

    async def test_add_photo(self, db_session, seed_data):
        photo_id = await CatalogAdminService.add_photo(1, 1, "new_file_id")

        product = await CatalogAdminService.get_product(1, 1)
        assert len(product["photos"]) == 1
        assert product["photos"][0]["file_id"] == "new_file_id"
        assert product["photos"][0]["position"] == 0

    async def test_add_photo_increments_position(self, db_session, seed_data):
        await CatalogAdminService.add_photo(1, 1, "file_1")
        await CatalogAdminService.add_photo(1, 1, "file_2")

        product = await CatalogAdminService.get_product(1, 1)
        assert product["photos"][0]["position"] == 0
        assert product["photos"][1]["position"] == 1

    async def test_delete_photo(self, db_session, seed_data):
        photo_id = await CatalogAdminService.add_photo(1, 1, "file_1")
        await CatalogAdminService.delete_photo(1, photo_id)

        product = await CatalogAdminService.get_product(1, 1)
        assert len(product["photos"]) == 0

    async def test_product_to_dict_includes_stock(self, db_session, seed_data):
        product = await CatalogAdminService.get_product(1, 1)

        assert "stock" in product["variants"][0]
        assert product["variants"][0]["stock"] == 10

    async def test_update_variant_stock(self, db_session, seed_data):
        ok = await CatalogAdminService.update_variant_stock(1, 1, 50)

        assert ok is True

        product = await CatalogAdminService.get_product(1, 1)
        assert product["variants"][0]["stock"] == 50

    async def test_update_variant_stock_not_found(self, db_session, seed_data):
        ok = await CatalogAdminService.update_variant_stock(1, 999, 50)

        assert ok is False

    async def test_update_variant_stock_clamps_negative(self, db_session, seed_data):
        await CatalogAdminService.update_variant_stock(1, 1, -5)

        product = await CatalogAdminService.get_product(1, 1)
        assert product["variants"][0]["stock"] == 0


class TestAdminOrders:

    async def test_get_orders_empty(self, db_session, seed_data):
        orders = await OrderAdminService.get_orders(1)

        assert orders == []

    async def test_get_orders(self, db_session, seed_data):
        from app.services.cart_service import CartService
        from app.services.order_service import OrderService

        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван Иванов",
            phone="+7 999",
            address="Москва",
        )

        orders = await OrderAdminService.get_orders(1)

        assert len(orders) == 1
        assert orders[0]["full_name"] == "Иван Иванов"

    async def test_get_order(self, db_session, seed_data):
        from app.services.cart_service import CartService
        from app.services.order_service import OrderService

        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=2)
        created = await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван",
            phone="+7",
            address="Адрес",
        )

        order = await OrderAdminService.get_order(1, created["order_id"])

        assert order is not None
        assert len(order["items"]) == 1
        assert order["items"][0]["quantity"] == 2

    async def test_get_order_not_found(self, db_session, seed_data):
        order = await OrderAdminService.get_order(1, 999)

        assert order is None

    async def test_set_order_status(self, db_session, seed_data):
        from app.services.cart_service import CartService
        from app.services.order_service import OrderService

        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        created = await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван",
            phone="+7",
            address="Адрес",
        )

        await OrderAdminService.set_order_status(1, created["order_id"], "confirmed")

        order = await OrderAdminService.get_order(1, created["order_id"])
        assert order["status"] == "confirmed"


class TestAdminStats:

    async def test_stats_empty(self, db_session, seed_data):
        stats = await StatsService.get_stats(1)

        assert stats["total_orders"] == 0
        assert stats["total_revenue"] == 0
        assert stats["top_products"] == []

    async def test_stats_with_orders(self, db_session, seed_data):
        from app.services.cart_service import CartService
        from app.services.order_service import OrderService

        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=2)
        await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван",
            phone="+7",
            address="Адрес",
        )

        await CartService.add_item(1, 111, product_id=3, variant_id=4, quantity=1)
        await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван",
            phone="+7",
            address="Адрес",
        )

        stats = await StatsService.get_stats(1)

        assert stats["total_orders"] == 2
        assert stats["new_orders"] == 2
        assert stats["total_revenue"] == 450 * 2 + 1290
        assert len(stats["top_products"]) == 2

    async def test_stats_excludes_cancelled_revenue(self, db_session, seed_data):
        from app.services.cart_service import CartService
        from app.services.order_service import OrderService

        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        created = await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван",
            phone="+7",
            address="Адрес",
        )

        await OrderAdminService.set_order_status(1, created["order_id"], "cancelled")

        stats = await StatsService.get_stats(1)

        assert stats["total_orders"] == 1
        assert stats["cancelled_orders"] == 1
        assert stats["total_revenue"] == 0


class TestAdminUsers:

    async def test_count_admins_empty(self, db_session, seed_data):
        count = await AdminUserService.count_admins(1)

        assert count == 0

    async def test_count_admins_with_records(self, db_session, seed_data):
        await AdminUserService.add(1, 100, "Админ 1")
        await AdminUserService.add(1, 200, "Админ 2")

        count = await AdminUserService.count_admins(1)

        assert count == 2

    async def test_count_admins_isolated_by_shop(self, db_session, seed_data):
        from app.models.shop import Shop

        async with db_session() as session:
            session.add(Shop(id=2, name="Shop 2", bot_token="x" * 64, bot_token_hash="x" * 32, owner_telegram_id=1))
            await session.commit()

        await AdminUserService.add(1, 100, "Админ 1")
        await AdminUserService.add(2, 200, "Админ 2")

        assert await AdminUserService.count_admins(1) == 1
        assert await AdminUserService.count_admins(2) == 1

    async def test_get_admin(self, db_session, seed_data):
        admin_id = await AdminUserService.add(1, 100, "Админ 1")

        admin = await AdminUserService.get(1, admin_id)

        assert admin is not None
        assert admin["id"] == admin_id
        assert admin["telegram_user_id"] == 100
        assert admin["display_name"] == "Админ 1"
        assert admin["is_super"] is False

    async def test_get_admin_wrong_shop(self, db_session, seed_data):
        admin_id = await AdminUserService.add(1, 100, "Админ 1")

        admin = await AdminUserService.get(999, admin_id)

        assert admin is None

    async def test_get_admin_not_found(self, db_session, seed_data):
        admin = await AdminUserService.get(1, 9999)

        assert admin is None

    async def test_delete_admin(self, db_session, seed_data):
        admin_id = await AdminUserService.add(1, 100, "Админ 1")

        ok = await AdminUserService.delete(1, admin_id)

        assert ok is True
        assert await AdminUserService.get(1, admin_id) is None
        assert await AdminUserService.count_admins(1) == 0

    async def test_delete_admin_wrong_shop(self, db_session, seed_data):
        admin_id = await AdminUserService.add(1, 100, "Админ 1")

        ok = await AdminUserService.delete(999, admin_id)

        assert ok is False

    async def test_get_all(self, db_session, seed_data):
        await AdminUserService.add(1, 100, "Админ 1")
        await AdminUserService.add(1, 200, "Админ 2")

        admins = await AdminUserService.get_all(1)

        assert len(admins) == 2
        assert all(a["is_super"] is False for a in admins)
