from sqlalchemy import select

from app.database.db import async_session
from app.models.product import Product
from app.models.review import Review


class ReviewAdminService:
    """Управление отзывами в админке."""

    @staticmethod
    async def get_all_reviews(shop_id: int) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Review)
                .where(Review.shop_id == shop_id)
                .order_by(Review.created_at.desc())
            )

            reviews = []
            for r in result.scalars().all():
                product_name = None
                if r.product_id:
                    prod_result = await session.execute(
                        select(Product.name).where(Product.id == r.product_id)
                    )
                    product_name = prod_result.scalar_one_or_none()

                reviews.append({
                    "id": r.id,
                    "product_id": r.product_id,
                    "product_name": product_name,
                    "telegram_user_id": r.telegram_user_id,
                    "rating": r.rating,
                    "text": r.text,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                })

            return reviews

    @staticmethod
    async def delete_review(shop_id: int, review_id: int) -> bool:
        async with async_session() as session:
            result = await session.execute(
                select(Review).where(
                    Review.shop_id == shop_id,
                    Review.id == review_id,
                )
            )
            review = result.scalar_one_or_none()

            if review:
                await session.delete(review)
                await session.commit()
                return True

            return False
