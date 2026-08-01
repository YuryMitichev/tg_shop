from app.models.cart_item import CartItem
from app.services.cart_service import CartService


class TestCartService:

    async def test_add_item(self, db_session, seed_data):
        await CartService.add_item(
            shop_id=1,
            telegram_user_id=111,
            product_id=1,
            variant_id=1,
            quantity=2,
        )

        items = await CartService.get_items(1, 111)

        assert len(items) == 1
        assert items[0]["product_name"] == "Кашемир"
        assert items[0]["volume"] == "75 г"
        assert items[0]["price"] == 450
        assert items[0]["quantity"] == 2
        assert items[0]["subtotal"] == 900

    async def test_add_same_item_increases_quantity(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=2)

        items = await CartService.get_items(1, 111)

        assert len(items) == 1
        assert items[0]["quantity"] == 3

    async def test_add_different_variants_separate(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        await CartService.add_item(1, 111, product_id=1, variant_id=2, quantity=1)

        items = await CartService.get_items(1, 111)

        assert len(items) == 2

    async def test_get_items_empty(self, db_session, seed_data):
        items = await CartService.get_items(1, 111)

        assert items == []

    async def test_change_quantity_increase(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        items = await CartService.get_items(1, 111)
        cart_item_id = items[0]["cart_item_id"]

        await CartService.change_quantity(1, 111, cart_item_id, delta=3)

        items = await CartService.get_items(1, 111)
        assert items[0]["quantity"] == 4

    async def test_change_quantity_to_zero_removes(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=2)
        items = await CartService.get_items(1, 111)
        cart_item_id = items[0]["cart_item_id"]

        await CartService.change_quantity(1, 111, cart_item_id, delta=-2)

        items = await CartService.get_items(1, 111)
        assert items == []

    async def test_change_quantity_wrong_user(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        items = await CartService.get_items(1, 111)
        cart_item_id = items[0]["cart_item_id"]

        await CartService.change_quantity(1, 222, cart_item_id, delta=5)

        items = await CartService.get_items(1, 111)
        assert items[0]["quantity"] == 1

    async def test_remove_item(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        items = await CartService.get_items(1, 111)
        cart_item_id = items[0]["cart_item_id"]

        await CartService.remove_item(1, 111, cart_item_id)

        items = await CartService.get_items(1, 111)
        assert items == []

    async def test_remove_item_wrong_user(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        items = await CartService.get_items(1, 111)
        cart_item_id = items[0]["cart_item_id"]

        await CartService.remove_item(1, 222, cart_item_id)

        items = await CartService.get_items(1, 111)
        assert len(items) == 1

    async def test_clear(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        await CartService.add_item(1, 111, product_id=1, variant_id=2, quantity=1)
        await CartService.add_item(1, 111, product_id=3, variant_id=4, quantity=1)

        await CartService.clear(1, 111)

        items = await CartService.get_items(1, 111)
        assert items == []

    async def test_clear_only_own_cart(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        await CartService.add_item(1, 222, product_id=1, variant_id=1, quantity=1)

        await CartService.clear(1, 111)

        items_111 = await CartService.get_items(1, 111)
        items_222 = await CartService.get_items(1, 222)
        assert items_111 == []
        assert len(items_222) == 1

    async def test_add_out_of_stock(self, db_session, seed_data):
        error = await CartService.add_item(1, 111, product_id=2, variant_id=3, quantity=1)

        assert error is not None
        assert "нет в наличии" in error

    async def test_add_exceeding_stock(self, db_session, seed_data):
        error = await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=15)

        assert error is not None
        assert "осталось" in error

    async def test_add_within_stock_ok(self, db_session, seed_data):
        error = await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=5)

        assert error is None
