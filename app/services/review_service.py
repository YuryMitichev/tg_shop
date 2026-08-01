from sqlalchemy import select, func

from app.database.db import async_session
from app.models.review import Review


class ReviewService:

    @staticmethod
    async def create_or_update(
        shop_id: int,
        product_id: int,
        telegram_user_id: int,
        rating: int,
        text: str | None = None,
    ) -> None:
        """Создаёт или обновляет отзыв пользователя о товаре."""
        async with async_session() as session:
            result = await session.execute(
                select(Review).where(
                    Review.shop_id == shop_id,
                    Review.product_id == product_id,
                    Review.telegram_user_id == telegram_user_id,
                )
            )
            review = result.scalar_one_or_none()

            if review:
                review.rating = rating
                review.text = text
            else:
                session.add(Review(
                    shop_id=shop_id,
                    product_id=product_id,
                    telegram_user_id=telegram_user_id,
                    rating=rating,
                    text=text,
                ))

            await session.commit()

    @staticmethod
    async def get_product_reviews(shop_id: int, product_id: int, limit: int = 5) -> list[dict]:
        """Последние отзывы о товаре."""
        async with async_session() as session:
            result = await session.execute(
                select(Review)
                .where(
                    Review.shop_id == shop_id,
                    Review.product_id == product_id,
                )
                .order_by(Review.created_at.desc())
                .limit(limit)
            )
            return [
                {
                    "rating": r.rating,
                    "text": r.text,
                }
                for r in result.scalars().all()
            ]

    @staticmethod
    async def get_rating_summary(shop_id: int, product_id: int) -> dict | None:
        """Средняя оценка и количество отзывов."""
        async with async_session() as session:
            result = await session.execute(
                select(
                    func.avg(Review.rating),
                    func.count(Review.id),
                )
                .where(
                    Review.shop_id == shop_id,
                    Review.product_id == product_id,
                )
            )
            avg, count = result.one()

            if count == 0:
                return None

            return {
                "avg": round(float(avg), 1),
                "count": count,
            }
