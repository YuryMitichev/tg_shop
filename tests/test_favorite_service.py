from sqlalchemy import func, select

from app.models.favorite import Favorite
from app.services.favorite_service import FavoriteService


class TestFavoriteService:
    async def test_add_list_and_remove(self, db_session, seed_data):
        assert await FavoriteService.add(1, 111, 1) is True
        assert await FavoriteService.list_product_ids(1, 111) == [1]
        assert await FavoriteService.product_ids(1, 111, [1, 3]) == {1}

        assert await FavoriteService.remove(1, 111, 1) is True
        assert await FavoriteService.list_product_ids(1, 111) == []

    async def test_add_is_idempotent(self, db_session, seed_data):
        assert await FavoriteService.add(1, 111, 1) is True
        assert await FavoriteService.add(1, 111, 1) is True

        async with db_session() as session:
            count = (
                await session.execute(
                    select(func.count()).select_from(Favorite).where(
                        Favorite.shop_id == 1,
                        Favorite.telegram_user_id == 111,
                        Favorite.product_id == 1,
                    )
                )
            ).scalar_one()
        assert count == 1

    async def test_users_are_isolated(self, db_session, seed_data):
        await FavoriteService.add(1, 111, 1)
        await FavoriteService.add(1, 222, 3)

        assert await FavoriteService.list_product_ids(1, 111) == [1]
        assert await FavoriteService.list_product_ids(1, 222) == [3]

    async def test_inactive_or_missing_product_cannot_be_added(
        self, db_session, seed_data
    ):
        assert await FavoriteService.add(1, 111, 2) is False
        assert await FavoriteService.add(1, 111, 999) is False

    async def test_inactive_product_disappears_but_relation_is_preserved(
        self, db_session, seed_data
    ):
        await FavoriteService.add(1, 111, 1)

        from app.models.product import Product

        async with db_session() as session:
            product = await session.get(Product, 1)
            product.is_active = False
            await session.commit()

        assert await FavoriteService.list_product_ids(1, 111) == []
        assert await FavoriteService.product_ids(1, 111, [1]) == {1}
