from app.services.admin_service import AdminService


class TestAdminCategories:

    async def test_get_categories(self, db_session, seed_data):
        categories = await AdminService.get_categories(1)

        assert len(categories) == 2

    async def test_create_category(self, db_session, seed_data):
        cat_id = await AdminService.create_category(1, "Аромалампы")

        categories = await AdminService.get_categories(1)
        assert len(categories) == 3
        assert any(c["name"] == "Аромалампы" for c in categories)

    async def test_create_category_with_emoji(self, db_session, seed_data):
        cat_id = await AdminService.create_category(1, "Саше", emoji="🌸")

        categories = await AdminService.get_categories(1)
        cat = next(c for c in categories if c["id"] == cat_id)
        assert cat["emoji"] == "🌸"

    async def test_update_category_emoji(self, db_session, seed_data):
        await AdminService.update_category_emoji(1, 1, "🔥")

        categories = await AdminService.get_categories(1)
        cat = next(c for c in categories if c["id"] == 1)
        assert cat["emoji"] == "🔥"

    async def test_update_category_emoji_remove(self, db_session, seed_data):
        await AdminService.update_category_emoji(1, 1, None)

        categories = await AdminService.get_categories(1)
        cat = next(c for c in categories if c["id"] == 1)
        assert cat["emoji"] is None

    async def test_rename_category(self, db_session, seed_data):
        await AdminService.rename_category(1, 1, "Свечи премиум")

        categories = await AdminService.get_categories(1)
        assert categories[0]["name"] == "Свечи премиум"

    async def test_count_products_in_category(self, db_session, seed_data):
        count = await AdminService.count_products_in_category(1, 1)

        assert count == 2

    async def test_count_products_empty_category(self, db_session, seed_data):
        cat_id = await AdminService.create_category(1, "Пустая")

        count = await AdminService.count_products_in_category(1, cat_id)

        assert count == 0

    async def test_delete_category_empty(self, db_session, seed_data):
        cat_id = await AdminService.create_category(1, "Пустая")

        ok = await AdminService.delete_category(1, cat_id)

        assert ok is True
        categories = await AdminService.get_categories(1)
        assert len(categories) == 2

    async def test_delete_category_with_products(self, db_session, seed_data):
        ok = await AdminService.delete_category(1, 1)

        assert ok is False
        categories = await AdminService.get_categories(1)
        assert len(categories) == 2


class TestAdminProducts:

    async def test_get_products_includes_hidden(self, db_session, seed_data):
        products = await AdminService.get_products(1, 1)

        assert len(products) == 2
        assert any(p["is_active"] is False for p in products)

    async def test_get_product(self, db_session, seed_data):
        product = await AdminService.get_product(1, 1)

        assert product is not None
        assert product["name"] == "Кашемир"

    async def test_get_product_not_found(self, db_session, seed_data):
        product = await AdminService.get_product(1, 999)

        assert product is None

    async def test_create_product(self, db_session, seed_data):
        product_id = await AdminService.create_product(
            shop_id=1,
            category_id=2,
            name="Новый диффузор",
            description="Описание",
            variants=[
                {"volume": "50 мл", "price": 690},
                {"volume": "100 мл", "price": 1190, "burn": None},
            ],
        )

        product = await AdminService.get_product(1, product_id)
        assert product["name"] == "Новый диффузор"
        assert len(product["variants"]) == 2

    async def test_create_product_with_photos(self, db_session, seed_data):
        product_id = await AdminService.create_product(
            shop_id=1,
            category_id=1,
            name="С фото",
            description="Описание",
            variants=[{"volume": "100 г", "price": 500}],
            photos=["file_id_1", "file_id_2"],
        )

        product = await AdminService.get_product(1, product_id)
        assert len(product["photos"]) == 2
        assert product["photos"][0]["file_id"] == "file_id_1"
        assert product["photos"][1]["position"] == 1

    async def test_delete_product(self, db_session, seed_data):
        await AdminService.delete_product(1, 1)

        product = await AdminService.get_product(1, 1)
        assert product is None

    async def test_toggle_active(self, db_session, seed_data):
        result = await AdminService.toggle_active(1, 1)

        assert result is False

        product = await AdminService.get_product(1, 1)
        assert product["is_active"] is False

    async def test_toggle_active_back(self, db_session, seed_data):
        await AdminService.toggle_active(1, 1)
        result = await AdminService.toggle_active(1, 1)

        assert result is True

    async def test_toggle_active_not_found(self, db_session, seed_data):
        result = await AdminService.toggle_active(1, 999)

        assert result is None

    async def test_update_product_name(self, db_session, seed_data):
        await AdminService.update_product(1, 1, name="Новое название")

        product = await AdminService.get_product(1, 1)
        assert product["name"] == "Новое название"
        assert product["description"] == "Теплый аромат"

    async def test_update_product_description(self, db_session, seed_data):
        await AdminService.update_product(1, 1, description="Новое описание")

        product = await AdminService.get_product(1, 1)
        assert product["description"] == "Новое описание"

    async def test_add_photo(self, db_session, seed_data):
        photo_id = await AdminService.add_photo(1, 1, "new_file_id")

        product = await AdminService.get_product(1, 1)
        assert len(product["photos"]) == 1
        assert product["photos"][0]["file_id"] == "new_file_id"
        assert product["photos"][0]["position"] == 0

    async def test_add_photo_increments_position(self, db_session, seed_data):
        await AdminService.add_photo(1, 1, "file_1")
        await AdminService.add_photo(1, 1, "file_2")

        product = await AdminService.get_product(1, 1)
        assert product["photos"][0]["position"] == 0
        assert product["photos"][1]["position"] == 1

    async def test_delete_photo(self, db_session, seed_data):
        photo_id = await AdminService.add_photo(1, 1, "file_1")
        await AdminService.delete_photo(1, photo_id)

        product = await AdminService.get_product(1, 1)
        assert len(product["photos"]) == 0

    async def test_product_to_dict_includes_stock(self, db_session, seed_data):
        product = await AdminService.get_product(1, 1)

        assert "stock" in product["variants"][0]
        assert product["variants"][0]["stock"] == 10

    async def test_update_variant_stock(self, db_session, seed_data):
        ok = await AdminService.update_variant_stock(1, 1, 50)

        assert ok is True

        product = await AdminService.get_product(1, 1)
        assert product["variants"][0]["stock"] == 50

    async def test_update_variant_stock_not_found(self, db_session, seed_data):
        ok = await AdminService.update_variant_stock(1, 999, 50)

        assert ok is False

    async def test_update_variant_stock_clamps_negative(self, db_session, seed_data):
        await AdminService.update_variant_stock(1, 1, -5)

        product = await AdminService.get_product(1, 1)
        assert product["variants"][0]["stock"] == 0


class TestAdminOrders:

    async def test_get_orders_empty(self, db_session, seed_data):
        orders = await AdminService.get_orders(1)

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

        orders = await AdminService.get_orders(1)

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

        order = await AdminService.get_order(1, created["order_id"])

        assert order is not None
        assert len(order["items"]) == 1
        assert order["items"][0]["quantity"] == 2

    async def test_get_order_not_found(self, db_session, seed_data):
        order = await AdminService.get_order(1, 999)

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

        await AdminService.set_order_status(1, created["order_id"], "confirmed")

        order = await AdminService.get_order(1, created["order_id"])
        assert order["status"] == "confirmed"


class TestAdminStats:

    async def test_stats_empty(self, db_session, seed_data):
        stats = await AdminService.get_stats(1)

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

        stats = await AdminService.get_stats(1)

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

        await AdminService.set_order_status(1, created["order_id"], "cancelled")

        stats = await AdminService.get_stats(1)

        assert stats["total_orders"] == 1
        assert stats["cancelled_orders"] == 1
        assert stats["total_revenue"] == 0
