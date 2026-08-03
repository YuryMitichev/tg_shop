import pytest
from sqlalchemy import select

from app.models.product_variant import ProductVariant
from app.models.promo_code import PromoCode
from app.models.cart_item import CartItem
from app.services.order_service import OrderService
from app.services.promo_service import PromoCodeService
from app.services.cart_service import CartService


class TestAtomicStock:
    """Тесты атомарного списания остатков."""

    async def test_create_order_decrements_stock(self, db_session, seed_data):
        await CartService.add_item(1, 100, product_id=1, variant_id=1, quantity=2)

        order = await OrderService.create_order(
            1, 100, "Тест", "+7999", "Адрес", payment_method="manual"
        )

        assert order is not None
        assert "error" not in order

        async with db_session() as session:
            variant = await session.get(ProductVariant, 1)
            assert variant.stock == 8

    async def test_create_order_out_of_stock(self, db_session, seed_data):
        async with db_session() as session:
            session.add(CartItem(
                shop_id=1, telegram_user_id=100,
                product_id=1, variant_id=2, quantity=10,
            ))
            await session.commit()

        order = await OrderService.create_order(
            1, 100, "Тест", "+7999", "Адрес", payment_method="manual"
        )

        assert order is not None
        assert order.get("error") == "out_of_stock"
        assert len(order["items"]) == 1
        assert order["items"][0]["available"] == 5

    async def test_create_order_partial_out_of_stock(self, db_session, seed_data):
        await CartService.add_item(1, 100, product_id=1, variant_id=1, quantity=1)

        async with db_session() as session:
            session.add(CartItem(
                shop_id=1, telegram_user_id=100,
                product_id=1, variant_id=2, quantity=10,
            ))
            await session.commit()

        order = await OrderService.create_order(
            1, 100, "Тест", "+7999", "Адрес", payment_method="manual"
        )

        assert order is not None
        assert order.get("error") == "out_of_stock"
        assert len(order["items"]) == 1
        assert order["items"][0]["requested"] == 10

    async def test_stock_not_changed_on_out_of_stock(self, db_session, seed_data):
        await CartService.add_item(1, 100, product_id=1, variant_id=1, quantity=1)

        async with db_session() as session:
            session.add(CartItem(
                shop_id=1, telegram_user_id=100,
                product_id=1, variant_id=2, quantity=10,
            ))
            await session.commit()

        await OrderService.create_order(
            1, 100, "Тест", "+7999", "Адрес", payment_method="manual"
        )

        async with db_session() as session:
            v1 = await session.get(ProductVariant, 1)
            v2 = await session.get(ProductVariant, 2)
            assert v1.stock == 10
            assert v2.stock == 5

    async def test_exact_stock_boundary(self, db_session, seed_data):
        await CartService.add_item(1, 100, product_id=1, variant_id=2, quantity=5)

        order = await OrderService.create_order(
            1, 100, "Тест", "+7999", "Адрес", payment_method="manual"
        )

        assert order is not None
        assert "error" not in order

        async with db_session() as session:
            v2 = await session.get(ProductVariant, 2)
            assert v2.stock == 0

    async def test_zero_stock_order(self, db_session, seed_data):
        async with db_session() as session:
            session.add(CartItem(
                shop_id=1, telegram_user_id=100,
                product_id=2, variant_id=3, quantity=1,
            ))
            await session.commit()

        order = await OrderService.create_order(
            1, 100, "Тест", "+7999", "Адрес", payment_method="manual"
        )

        assert order is not None
        assert order.get("error") == "out_of_stock"
        assert order["items"][0]["available"] == 0


class TestAtomicPromoCode:
    """Тесты атомарности промокодов."""

    async def test_try_increment_success(self, db_session, seed_data):
        await PromoCodeService.create(1, "ATOMIC1", "percent", 10, max_uses=3)

        async with db_session() as session:
            ok = await PromoCodeService.try_increment_usage(session, 1, "ATOMIC1")
            await session.commit()

        assert ok is True

        async with db_session() as session:
            result = await session.execute(
                select(PromoCode).where(PromoCode.code == "ATOMIC1")
            )
            promo = result.scalar_one()
            assert promo.used_count == 1

    async def test_try_increment_limit_reached(self, db_session, seed_data):
        await PromoCodeService.create(1, "ATOMIC2", "percent", 10, max_uses=1)

        async with db_session() as session:
            ok1 = await PromoCodeService.try_increment_usage(session, 1, "ATOMIC2")
            await session.commit()

        async with db_session() as session:
            ok2 = await PromoCodeService.try_increment_usage(session, 1, "ATOMIC2")
            await session.commit()

        assert ok1 is True
        assert ok2 is False

    async def test_try_increment_unlimited(self, db_session, seed_data):
        await PromoCodeService.create(1, "ATOMIC3", "percent", 10, max_uses=None)

        for _ in range(5):
            async with db_session() as session:
                ok = await PromoCodeService.try_increment_usage(session, 1, "ATOMIC3")
                await session.commit()
            assert ok is True

    async def test_order_with_promo_out_of_stock_no_increment(
        self, db_session, seed_data
    ):
        await PromoCodeService.create(1, "STOCKPROMO", "percent", 10, max_uses=1)

        async with db_session() as session:
            session.add(CartItem(
                shop_id=1, telegram_user_id=100,
                product_id=2, variant_id=3, quantity=1,
            ))
            await session.commit()

        order = await OrderService.create_order(
            1,
            100,
            "Тест",
            "+7999",
            "Адрес",
            promo_code="STOCKPROMO",
            payment_method="manual",
        )

        assert order.get("error") == "out_of_stock"

        async with db_session() as session:
            result = await session.execute(
                select(PromoCode).where(PromoCode.code == "STOCKPROMO")
            )
            promo = result.scalar_one()
            assert promo.used_count == 0
