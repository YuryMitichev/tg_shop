import json

from sqlalchemy import select

from app.database.db import async_session
from app.models.shop import Shop
from app.utils.crypto import decrypt, encrypt, mask_token, token_hash


def _shop_to_dict(shop: Shop) -> dict:
    return {
        "id": shop.id,
        "name": shop.name,
        "bot_token_masked": mask_token(decrypt(shop.bot_token) or ""),
        "owner_telegram_id": shop.owner_telegram_id,
        "is_active": shop.is_active,
        "delivery_enabled": shop.delivery_enabled,
        "courier_services": json.loads(shop.courier_services) if shop.courier_services else [],
        "product_attrs": json.loads(shop.product_attrs) if shop.product_attrs else ["volume"],
        "company_name": shop.company_name,
        "company_inn": shop.company_inn,
        "company_address": shop.company_address,
        "created_at": shop.created_at.isoformat() if shop.created_at else None,
    }


class ShopService:
    """
    CRUD для магазинов (SaaS).

    bot_token хранится зашифрованным (Fernet).
    Расшифровка — только через get_bot_token() при создании Bot.
    """

    _token_cache: dict[int, str] = {}

    @classmethod
    async def get_bot_token(cls, shop_id: int) -> str | None:
        """Возвращает расшифрованный bot_token (с кешированием)."""
        if shop_id in cls._token_cache:
            return cls._token_cache[shop_id]

        async with async_session() as session:
            shop = await session.get(Shop, shop_id)
            if shop is None:
                return None
            plaintext = decrypt(shop.bot_token)
            if plaintext is None:
                return None

        cls._token_cache[shop_id] = plaintext
        return plaintext

    @classmethod
    def invalidate_token_cache(cls, shop_id: int | None = None) -> None:
        """Сбрасывает кеш токенов (всех или конкретного магазина)."""
        if shop_id is not None:
            cls._token_cache.pop(shop_id, None)
        else:
            cls._token_cache.clear()

    @staticmethod
    async def create(
        name: str,
        bot_token: str,
        owner_telegram_id: int,
    ) -> dict:
        async with async_session() as session:
            shop = Shop(
                name=name,
                bot_token=encrypt(bot_token),
                bot_token_hash=token_hash(bot_token),
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
                shop.bot_token = encrypt(bot_token)
                shop.bot_token_hash = token_hash(bot_token)
            if owner_telegram_id is not None:
                shop.owner_telegram_id = owner_telegram_id
            if is_active is not None:
                shop.is_active = is_active

            await session.commit()
            await session.refresh(shop)

            if bot_token is not None:
                ShopService.invalidate_token_cache(shop_id)

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
        """Ищет магазин по хэшу токена."""
        async with async_session() as session:
            result = await session.execute(
                select(Shop).where(Shop.bot_token_hash == token_hash(bot_token))
            )
            shop = result.scalar_one_or_none()
            if shop is None:
                return None
            return _shop_to_dict(shop)

    @staticmethod
    async def update_delivery_settings(
        shop_id: int,
        delivery_enabled: bool,
        courier_services: list[str],
    ) -> dict | None:
        async with async_session() as session:
            shop = await session.get(Shop, shop_id)
            if shop is None:
                return None

            shop.delivery_enabled = delivery_enabled
            shop.courier_services = json.dumps(courier_services, ensure_ascii=False)

            await session.commit()
            await session.refresh(shop)

            return _shop_to_dict(shop)

    @staticmethod
    async def update_product_attrs(
        shop_id: int,
        product_attrs: list[str],
    ) -> dict | None:
        async with async_session() as session:
            shop = await session.get(Shop, shop_id)
            if shop is None:
                return None

            shop.product_attrs = json.dumps(product_attrs, ensure_ascii=False)

            await session.commit()
            await session.refresh(shop)

            return _shop_to_dict(shop)

    @staticmethod
    async def update_company_info(
        shop_id: int,
        company_name: str | None,
        company_inn: str | None,
        company_address: str | None,
    ) -> dict | None:
        async with async_session() as session:
            shop = await session.get(Shop, shop_id)
            if shop is None:
                return None

            shop.company_name = company_name
            shop.company_inn = company_inn
            shop.company_address = company_address

            await session.commit()
            await session.refresh(shop)

            return _shop_to_dict(shop)
