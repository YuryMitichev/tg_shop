from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.database.db import async_session
from app.models.favorite import Favorite
from app.models.product import Product


class FavoriteService:
    @staticmethod
    async def list_product_ids(shop_id: int, telegram_user_id: int) -> list[int]:
        async with async_session() as session:
            result = await session.execute(
                select(Favorite.product_id)
                .join(
                    Product,
                    (Product.id == Favorite.product_id)
                    & (Product.shop_id == Favorite.shop_id),
                )
                .where(
                    Favorite.shop_id == shop_id,
                    Favorite.telegram_user_id == telegram_user_id,
                    Product.is_active == True,  # noqa: E712
                )
                .order_by(Favorite.created_at.desc(), Favorite.id.desc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def product_ids(
        shop_id: int,
        telegram_user_id: int,
        product_ids: Iterable[int] | None = None,
    ) -> set[int]:
        stmt = select(Favorite.product_id).where(
            Favorite.shop_id == shop_id,
            Favorite.telegram_user_id == telegram_user_id,
        )
        if product_ids is not None:
            ids = list(product_ids)
            if not ids:
                return set()
            stmt = stmt.where(Favorite.product_id.in_(ids))

        async with async_session() as session:
            result = await session.execute(stmt)
            return set(result.scalars().all())

    @staticmethod
    async def add(shop_id: int, telegram_user_id: int, product_id: int) -> bool:
        async with async_session() as session:
            product = (
                await session.execute(
                    select(Product.id).where(
                        Product.shop_id == shop_id,
                        Product.id == product_id,
                        Product.is_active == True,  # noqa: E712
                    )
                )
            ).scalar_one_or_none()
            if product is None:
                return False

            existing = (
                await session.execute(
                    select(Favorite.id).where(
                        Favorite.shop_id == shop_id,
                        Favorite.telegram_user_id == telegram_user_id,
                        Favorite.product_id == product_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return True

            session.add(
                Favorite(
                    shop_id=shop_id,
                    telegram_user_id=telegram_user_id,
                    product_id=product_id,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                # Два быстрых нажатия могут одновременно создать одну запись.
                # Уникальный ключ делает операцию идемпотентной.
                await session.rollback()
                existing = (
                    await session.execute(
                        select(Favorite.id).where(
                            Favorite.shop_id == shop_id,
                            Favorite.telegram_user_id == telegram_user_id,
                            Favorite.product_id == product_id,
                        )
                    )
                ).scalar_one_or_none()
                return existing is not None
            return True

    @staticmethod
    async def remove(shop_id: int, telegram_user_id: int, product_id: int) -> bool:
        async with async_session() as session:
            result = await session.execute(
                delete(Favorite).where(
                    Favorite.shop_id == shop_id,
                    Favorite.telegram_user_id == telegram_user_id,
                    Favorite.product_id == product_id,
                )
            )
            await session.commit()
            return bool(result.rowcount)
