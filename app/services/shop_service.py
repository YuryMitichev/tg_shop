import json

from sqlalchemy import select

from app.database.db import async_session
from app.models.shop import Shop
from app.utils.crypto import decrypt, encrypt, mask_token, token_hash


def _mask_secret_key(key: str | None) -> str | None:
    """Маскирует секретный ключ: 'live_abcdef123456' → '****3456'."""
    if not key:
        return None
    if len(key) <= 4:
        return "****"
    return f"****{key[-4:]}"


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
        "payment_card_number": shop.payment_card_number,
        "payment_recipient_name": shop.payment_recipient_name,
        "yookassa_shop_id": shop.yookassa_shop_id,
        "yookassa_secret_key_masked": _mask_secret_key(decrypt(shop.yookassa_secret_key) if shop.yookassa_secret_key else None),
        "yookassa_enabled": shop.yookassa_enabled,
        "manual_payment_enabled": shop.manual_payment_enabled,
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

    @staticmethod
    async def update_payment_settings(
        shop_id: int,
        payment_card_number: str | None = None,
        payment_recipient_name: str | None = None,
        yookassa_shop_id: str | None = None,
        yookassa_secret_key: str | None = None,
        yookassa_enabled: bool | None = None,
        manual_payment_enabled: bool | None = None,
    ) -> dict | None:
        """
        Обновляет платёжные настройки магазина.

        None означает «не менять». Пустая строка — очистить поле.
        yookassa_secret_key шифруется (Fernet) перед сохранением.
        """
        async with async_session() as session:
            shop = await session.get(Shop, shop_id)
            if shop is None:
                return None

            if payment_card_number is not None:
                shop.payment_card_number = payment_card_number or None

            if payment_recipient_name is not None:
                shop.payment_recipient_name = payment_recipient_name or None

            if yookassa_shop_id is not None:
                shop.yookassa_shop_id = yookassa_shop_id or None

            if yookassa_secret_key is not None:
                shop.yookassa_secret_key = encrypt(yookassa_secret_key) if yookassa_secret_key else None

            if yookassa_enabled is not None:
                shop.yookassa_enabled = yookassa_enabled

            if manual_payment_enabled is not None:
                shop.manual_payment_enabled = manual_payment_enabled

            await session.commit()
            await session.refresh(shop)

            return _shop_to_dict(shop)

    @staticmethod
    async def get_yookassa_credentials(shop_id: int) -> tuple[str, str] | None:
        """
        Возвращает расшифрованные ключи ЮKassa для магазина.

        Используется OrderPaymentService и вебхуком для per-shop платежей.
        Возвращает (shop_id_key, secret_key) или None.
        """
        async with async_session() as session:
            shop = await session.get(Shop, shop_id)
            if shop is None:
                return None

            if not shop.yookassa_shop_id or not shop.yookassa_secret_key:
                return None

            secret = decrypt(shop.yookassa_secret_key)
            if secret is None:
                return None

            return (shop.yookassa_shop_id, secret)
