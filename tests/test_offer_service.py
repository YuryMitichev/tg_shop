from datetime import datetime, timedelta

from app.services.offer_service import OfferService


class TestCalcDiscountedPrice:

    def test_basic_discount(self):
        assert OfferService.calc_discounted_price(1000, 10) == 900

    def test_zero_discount(self):
        assert OfferService.calc_discounted_price(500, 0) == 500

    def test_full_discount(self):
        assert OfferService.calc_discounted_price(1000, 100) == 0

    def test_rounds_down(self):
        assert OfferService.calc_discounted_price(995, 15) == 845


class TestCreateOffer:

    async def test_create_offer(self, db_session, seed_data):
        offer = await OfferService.create_offer(
            shop_id=1,
            telegram_user_id=111,
            product_id=1,
            discount_percent=15,
        )
        assert offer.id is not None
        assert offer.is_active is True
        assert offer.discount_percent == 15

    async def test_create_offer_with_variant(self, db_session, seed_data):
        offer = await OfferService.create_offer(
            shop_id=1,
            telegram_user_id=111,
            product_id=1,
            discount_percent=10,
            variant_id=1,
        )
        assert offer.variant_id == 1


class TestGetBestOffer:

    async def test_no_offers(self, db_session, seed_data):
        result = await OfferService.get_best_offer(1, 111, 1)
        assert result is None

    async def test_returns_highest_discount(self, db_session, seed_data):
        await OfferService.create_offer(1, 111, 1, 10)
        await OfferService.create_offer(1, 111, 1, 25)
        await OfferService.create_offer(1, 111, 1, 5)

        best = await OfferService.get_best_offer(1, 111, 1)
        assert best.discount_percent == 25

    async def test_prefers_variant_specific(self, db_session, seed_data):
        await OfferService.create_offer(1, 111, 1, 20, variant_id=None)
        await OfferService.create_offer(1, 111, 1, 10, variant_id=1)

        best = await OfferService.get_best_offer(1, 111, 1, variant_id=1)
        assert best.discount_percent == 10
        assert best.variant_id == 1

    async def test_falls_back_to_generic(self, db_session, seed_data):
        await OfferService.create_offer(1, 111, 1, 20, variant_id=None)

        best = await OfferService.get_best_offer(1, 111, 1, variant_id=1)
        assert best is not None
        assert best.variant_id is None

    async def test_ignores_expired(self, db_session, seed_data):
        await OfferService.create_offer(
            1, 111, 1, 50,
            expires_at=datetime.now() - timedelta(hours=1),
        )

        best = await OfferService.get_best_offer(1, 111, 1)
        assert best is None

    async def test_ignores_inactive(self, db_session, seed_data):
        offer = await OfferService.create_offer(1, 111, 1, 30)
        await OfferService.mark_used(1, 111, 1, variant_id=None)

        best = await OfferService.get_best_offer(1, 111, 1)
        assert best is None


class TestApplyToVariants:

    async def test_no_user_returns_original(self, db_session, seed_data):
        variants = [{"id": 1, "price": 450}, {"id": 2, "price": 990}]
        result = await OfferService.apply_to_variants(1, None, 1, variants)
        assert result == variants

    async def test_applies_discount(self, db_session, seed_data):
        await OfferService.create_offer(1, 111, 1, 20, variant_id=1)

        variants = [{"id": 1, "price": 450}, {"id": 2, "price": 990}]
        result = await OfferService.apply_to_variants(1, 111, 1, variants)

        assert result[0]["price"] == 360
        assert result[0]["original_price"] == 450
        assert result[0]["discount_percent"] == 20
        assert result[1]["price"] == 990
        assert "original_price" not in result[1]


class TestMarkUsed:

    async def test_mark_used_deactivates(self, db_session, seed_data):
        await OfferService.create_offer(1, 111, 1, 15, variant_id=1)
        await OfferService.mark_used(1, 111, 1, 1)

        best = await OfferService.get_best_offer(1, 111, 1, variant_id=1)
        assert best is None


class TestGetUserOffers:

    async def test_returns_active_only(self, db_session, seed_data):
        await OfferService.create_offer(1, 111, 1, 10, variant_id=1)
        await OfferService.create_offer(1, 111, 1, 20, variant_id=2)
        await OfferService.create_offer(1, 111, 1, 30, variant_id=1,
                                        expires_at=datetime.now() - timedelta(hours=1))

        offers = await OfferService.get_user_offers(1, 111)
        assert len(offers) == 2

    async def test_empty(self, db_session, seed_data):
        offers = await OfferService.get_user_offers(1, 999)
        assert offers == []
