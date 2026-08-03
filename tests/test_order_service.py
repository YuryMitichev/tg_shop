from app.services.cart_service import CartService
from app.services.order_service import OrderService
from app.models.product_variant import ProductVariant


class TestOrderService:

    async def test_create_order(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=2)
        await CartService.add_item(1, 111, product_id=3, variant_id=4, quantity=1)

        result = await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван Иванов",
            phone="+7 999 123-45-67",
            address="г. Москва, ул. Тверская, д. 1",
        )

        assert result is not None
        assert result["order_id"] == 1
        assert result["total"] == 450 * 2 + 1290
        assert len(result["items"]) == 2
        assert result["full_name"] == "Иван Иванов"

    async def test_create_order_with_comment(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)

        result = await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван Иванов",
            phone="+7 999 123-45-67",
            address="г. Москва",
            comment="Позвонить перед доставкой",
        )

        assert result["comment"] == "Позвонить перед доставкой"

    async def test_create_order_empty_cart(self, db_session, seed_data):
        result = await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван Иванов",
            phone="+7 999 123-45-67",
            address="г. Москва",
        )

        assert result is None

    async def test_create_order_clears_cart(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)

        await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван Иванов",
            phone="+7 999 123-45-67",
            address="г. Москва",
        )

        items = await CartService.get_items(1, 111)
        assert items == []

    async def test_get_user_orders(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван",
            phone="+7",
            address="Адрес",
        )

        orders = await OrderService.get_user_orders(1, 111)

        assert len(orders) == 1
        assert orders[0]["status"] == "new"
        assert orders[0]["total_amount"] == 450

    async def test_get_user_orders_empty(self, db_session, seed_data):
        orders = await OrderService.get_user_orders(1, 111)

        assert orders == []

    async def test_get_user_order(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=2)

        created = await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван Иванов",
            phone="+7 999",
            address="Адрес",
            comment="Комментарий",
        )

        order = await OrderService.get_user_order(1, 111, created["order_id"])

        assert order is not None
        assert order["full_name"] == "Иван Иванов"
        assert order["comment"] == "Комментарий"
        assert len(order["items"]) == 1
        assert order["items"][0]["product_name"] == "Кашемир"
        assert order["items"][0]["quantity"] == 2

    async def test_get_user_order_not_found(self, db_session, seed_data):
        order = await OrderService.get_user_order(1, 111, 999)

        assert order is None

    async def test_get_user_order_wrong_user(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)

        created = await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван",
            phone="+7",
            address="Адрес",
        )

        order = await OrderService.get_user_order(1, 222, created["order_id"])

        assert order is None

    async def test_order_decreases_stock(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=3)

        await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван",
            phone="+7",
            address="Адрес",
        )

        async with db_session() as session:
            variant = await session.get(ProductVariant, 1)
            assert variant.stock == 7

    async def test_cancel_returns_stock(self, db_session, seed_data):
        from app.services.order_admin_service import OrderAdminService

        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=3)

        created = await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван",
            phone="+7",
            address="Адрес",
        )

        async with db_session() as session:
            variant = await session.get(ProductVariant, 1)
            assert variant.stock == 7

        await OrderAdminService.set_order_status(1, created["order_id"], "cancelled")

        async with db_session() as session:
            variant = await session.get(ProductVariant, 1)
            assert variant.stock == 10

    async def test_auto_cancel_stale_orders(self, db_session, seed_data):
        from datetime import datetime, timedelta

        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=2)

        created = await OrderService.create_order(
            shop_id=1,
            telegram_user_id=111,
            full_name="Иван",
            phone="+7",
            address="Адрес",
        )

        async with db_session() as session:
            from app.models.order import Order
            order = await session.get(Order, created["order_id"])
            order.created_at = datetime.now() - timedelta(days=15)
            await session.commit()

        cancelled = await OrderService.auto_cancel_stale_orders(days=14)

        assert cancelled == 1

        async with db_session() as session:
            variant = await session.get(ProductVariant, 1)
            assert variant.stock == 10
