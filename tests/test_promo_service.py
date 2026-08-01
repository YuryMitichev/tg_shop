from app.services.promo_service import PromoCodeService


class TestPromoService:

    async def test_create_promo_percent(self, db_session, seed_data):
        promo_id = await PromoCodeService.create(
            shop_id=1,
            code="NEW10",
            discount_type="percent",
            discount_value=10,
        )

        promos = await PromoCodeService.get_all(1)
        assert len(promos) == 1
        assert promos[0]["code"] == "NEW10"

    async def test_validate_percent(self, db_session, seed_data):
        await PromoCodeService.create(1, "SAVE20", "percent", 20)

        result = await PromoCodeService.validate(1, "SAVE20", 1000)

        assert result is not None
        assert result["discount_amount"] == 200
        assert result["final_total"] == 800

    async def test_validate_fixed(self, db_session, seed_data):
        await PromoCodeService.create(1, "500RUB", "fixed", 500)

        result = await PromoCodeService.validate(1, "500RUB", 1000)

        assert result is not None
        assert result["discount_amount"] == 500
        assert result["final_total"] == 500

    async def test_validate_fixed_exceeds_total(self, db_session, seed_data):
        await PromoCodeService.create(1, "BIG1000", "fixed", 1000)

        result = await PromoCodeService.validate(1, "BIG1000", 300)

        assert result["discount_amount"] == 300
        assert result["final_total"] == 0

    async def test_validate_case_insensitive(self, db_session, seed_data):
        await PromoCodeService.create(1, "SUMMER", "percent", 15)

        result = await PromoCodeService.validate(1, "summer", 1000)

        assert result is not None
        assert result["discount_amount"] == 150

    async def test_validate_not_found(self, db_session, seed_data):
        result = await PromoCodeService.validate(1, "UNKNOWN", 1000)
        assert result is None

    async def test_validate_inactive(self, db_session, seed_data):
        promo_id = await PromoCodeService.create(1, "OFF", "percent", 50)
        await PromoCodeService.toggle_active(1, promo_id)

        result = await PromoCodeService.validate(1, "OFF", 1000)
        assert result is None

    async def test_validate_max_uses_reached(self, db_session, seed_data):
        promo_id = await PromoCodeService.create(1, "LIMIT", "percent", 10, max_uses=2)

        await PromoCodeService.increment_usage(1, "LIMIT")
        await PromoCodeService.increment_usage(1, "LIMIT")

        result = await PromoCodeService.validate(1, "LIMIT", 1000)
        assert result is None

    async def test_increment_usage(self, db_session, seed_data):
        await PromoCodeService.create(1, "COUNT", "percent", 5, max_uses=10)

        await PromoCodeService.increment_usage(1, "COUNT")
        await PromoCodeService.increment_usage(1, "COUNT")

        promos = await PromoCodeService.get_all(1)
        assert promos[0]["used_count"] == 2

    async def test_toggle_active(self, db_session, seed_data):
        promo_id = await PromoCodeService.create(1, "TOGGLE", "percent", 10)

        await PromoCodeService.toggle_active(1, promo_id)
        promos = await PromoCodeService.get_all(1)
        assert promos[0]["is_active"] is False

        await PromoCodeService.toggle_active(1, promo_id)
        promos = await PromoCodeService.get_all(1)
        assert promos[0]["is_active"] is True

    async def test_delete(self, db_session, seed_data):
        promo_id = await PromoCodeService.create(1, "TEMP", "percent", 10)

        await PromoCodeService.delete(1, promo_id)

        promos = await PromoCodeService.get_all(1)
        assert len(promos) == 0
