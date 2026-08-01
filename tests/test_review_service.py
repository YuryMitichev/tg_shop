from app.services.review_service import ReviewService


class TestReviewService:

    async def test_create_review(self, db_session, seed_data):
        await ReviewService.create_or_update(
            shop_id=1,
            product_id=1,
            telegram_user_id=100,
            rating=5,
            text="Отличная свеча!",
        )

        summary = await ReviewService.get_rating_summary(1, 1)
        assert summary["avg"] == 5.0
        assert summary["count"] == 1

    async def test_create_review_no_text(self, db_session, seed_data):
        await ReviewService.create_or_update(
            shop_id=1,
            product_id=1,
            telegram_user_id=100,
            rating=4,
        )

        reviews = await ReviewService.get_product_reviews(1, 1)
        assert len(reviews) == 1
        assert reviews[0]["rating"] == 4
        assert reviews[0]["text"] is None

    async def test_update_review(self, db_session, seed_data):
        await ReviewService.create_or_update(1, 1, 100, 5, "Супер")
        await ReviewService.create_or_update(1, 1, 100, 3, "Передумал")

        summary = await ReviewService.get_rating_summary(1, 1)
        assert summary["count"] == 1
        assert summary["avg"] == 3.0

        reviews = await ReviewService.get_product_reviews(1, 1)
        assert reviews[0]["text"] == "Передумал"

    async def test_multiple_reviews_avg(self, db_session, seed_data):
        await ReviewService.create_or_update(1, 1, 100, 5)
        await ReviewService.create_or_update(1, 1, 101, 4)
        await ReviewService.create_or_update(1, 1, 102, 3)

        summary = await ReviewService.get_rating_summary(1, 1)
        assert summary["count"] == 3
        assert summary["avg"] == 4.0

    async def test_no_reviews(self, db_session, seed_data):
        summary = await ReviewService.get_rating_summary(1, 1)
        assert summary is None

    async def test_reviews_isolated_per_product(self, db_session, seed_data):
        await ReviewService.create_or_update(1, 1, 100, 5)
        await ReviewService.create_or_update(1, 3, 100, 2)

        s1 = await ReviewService.get_rating_summary(1, 1)
        s3 = await ReviewService.get_rating_summary(1, 3)

        assert s1["avg"] == 5.0
        assert s3["avg"] == 2.0
