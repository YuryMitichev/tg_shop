from app.services.promo_service import PromoCodeService


class TestPromoService:

    async def test_create_promo_percent(self, db_session, seed_data):
        promo_id = await PromoCodeService.create(
            code="NEW10",
            discount_type="percent",
            discount_value=10,
        )

        promos = await PromoCodeService.get_all()
        assert len(promos) == 1
        assert promos[0]["code"] == "NEW10"

    async def test_validate_percent(self, db_session, seed_data):
        await PromoCodeService.create("SAVE20", "percent", 20)

        result = await PromoCodeService.validate("SAVE20", 1000)

        assert result is not None
        assert result["discount_amount"] == 200
        assert result["final_total"] == 800

    async def test_validate_fixed(self, db_session, seed_data):
        await PromoCodeService.create("500RUB", "fixed", 500)

        result = await PromoCodeService.validate("500RUB", 1000)

        assert result is not None
        assert result["discount_amount"] == 500
        assert result["final_total"] == 500

    async def test_validate_fixed_exceeds_total(self, db_session, seed_data):
        await PromoCodeService.create("BIG1000", "fixed", 1000)

        result = await PromoCodeService.validate("BIG1000", 300)

        assert result["discount_amount"] == 300
        assert result["final_total"] == 0

    async def test_validate_case_insensitive(self, db_session, seed_data):
        await PromoCodeService.create("SUMMER", "percent", 15)

        result = await PromoCodeService.validate("summer", 1000)

        assert result is not None
        assert result["discount_amount"] == 150

    async def test_validate_not_found(self, db_session, seed_data):
        result = await PromoCodeService.validate("UNKNOWN", 1000)
        assert result is None

    async def test_validate_inactive(self, db_session, seed_data):
        promo_id = await PromoCodeService.create("OFF", "percent", 50)
        await PromoCodeService.toggle_active(promo_id)

        result = await PromoCodeService.validate("OFF", 1000)
        assert result is None

    async def test_validate_max_uses_reached(self, db_session, seed_data):
        promo_id = await PromoCodeService.create("LIMIT", "percent", 10, max_uses=2)

        await PromoCodeService.increment_usage("LIMIT")
        await PromoCodeService.increment_usage("LIMIT")

        result = await PromoCodeService.validate("LIMIT", 1000)
        assert result is None

    async def test_increment_usage(self, db_session, seed_data):
        await PromoCodeService.create("COUNT", "percent", 5, max_uses=10)

        await PromoCodeService.increment_usage("COUNT")
        await PromoCodeService.increment_usage("COUNT")

        promos = await PromoCodeService.get_all()
        assert promos[0]["used_count"] == 2

    async def test_toggle_active(self, db_session, seed_data):
        promo_id = await PromoCodeService.create("TOGGLE", "percent", 10)

        await PromoCodeService.toggle_active(promo_id)
        promos = await PromoCodeService.get_all()
        assert promos[0]["is_active"] is False

        await PromoCodeService.toggle_active(promo_id)
        promos = await PromoCodeService.get_all()
        assert promos[0]["is_active"] is True

    async def test_delete(self, db_session, seed_data):
        promo_id = await PromoCodeService.create("TEMP", "percent", 10)

        await PromoCodeService.delete(promo_id)

        promos = await PromoCodeService.get_all()
        assert len(promos) == 0
