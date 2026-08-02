from sqlalchemy import select

from app.database.db import async_session
from app.models.shop import Shop


def _shop_to_dict(shop: Shop) -> dict:
    return {
        "id": shop.id,
        "name": shop.name,
        "bot_token": shop.bot_token,
        "owner_telegram_id": shop.owner_telegram_id,
        "is_active": shop.is_active,
        "created_at": shop.created_at.isoformat() if shop.created_at else None,
    }


class ShopService:
    """
    CRUD для магазинов (SaaS).

    Только супер-админ имеет доступ к этим операциям.
    """

    @staticmethod
    async def create(
        name: str,
        bot_token: str,
        owner_telegram_id: int,
    ) -> dict:
        async with async_session() as session:
            shop = Shop(
                name=name,
                bot_token=bot_token,
                owner_telegram_id=owner_telegram_id,
                is_active=True,
            )
            session.add(shop)
            await session.commit()
            await session.refresh(shop)
            return _shop_to_dict(shop)

    @staticmethod
    async def get_all(active_only: bool = False) -> list[dict]:
        async with async_session() as session:
            stmt = select(Shop).order_by(Shop.id)
            if active_only:
                stmt = stmt.where(Shop.is_active == True)  # noqa: E712
            result = await session.execute(stmt)
            return [_shop_to_dict(s) for s in result.scalars().all()]

    @staticmethod
    async def get(shop_id: int) -> dict | None:
        async with async_session() as session:
            shop = await session.get(Shop, shop_id)
            if shop is None:
                return None
            return _shop_to_dict(shop)

    @staticmethod
    async def update(
        shop_id: int,
        name: str | None = None,
        bot_token: str | None = None,
        owner_telegram_id: int | None = None,
        is_active: bool | None = None,
    ) -> dict | None:
        async with async_session() as session:
            shop = await session.get(Shop, shop_id)
            if shop is None:
                return None

            if name is not None:
                shop.name = name
            if bot_token is not None:
                shop.bot_token = bot_token
            if owner_telegram_id is not None:
                shop.owner_telegram_id = owner_telegram_id
            if is_active is not None:
                shop.is_active = is_active

            await session.commit()
            await session.refresh(shop)
            return _shop_to_dict(shop)

    @staticmethod
    async def delete(shop_id: int) -> bool:
        if shop_id == 1:
            return False

        async with async_session() as session:
            shop = await session.get(Shop, shop_id)
            if shop is None:
                return False

            await session.delete(shop)
            await session.commit()
            return True

    @staticmethod
    async def get_by_bot_token(bot_token: str) -> dict | None:
        async with async_session() as session:
            result = await session.execute(
                select(Shop).where(Shop.bot_token == bot_token)
            )
            shop = result.scalar_one_or_none()
            if shop is None:
                return None
            return _shop_to_dict(shop)
