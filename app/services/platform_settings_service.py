import logging

from app.core.config import settings
from app.database.db import async_session
from app.models.platform_settings import PlatformSettings
from app.utils.crypto import decrypt, encrypt

logger = logging.getLogger(__name__)


def _mask_secret_key(key: str | None) -> str | None:
    """Маскирует секретный ключ: 'live_abcdef123456' → '****3456'."""
    if not key:
        return None
    if len(key) <= 4:
        return "****"
    return f"****{key[-4:]}"


class PlatformSettingsService:
    """Управление глобальными настройками платформы."""

    @staticmethod
    async def get_settings() -> dict:
        """Возвращает настройки платежей платформы для отображения."""
        async with async_session() as session:
            settings_obj = await session.get(PlatformSettings, 1)
            if settings_obj is None:
                return {
                    "yookassa_shop_id": None,
                    "yookassa_secret_key_masked": None,
                    "yookassa_enabled": False,
                }

            secret = (
                decrypt(settings_obj.yookassa_secret_key)
                if settings_obj.yookassa_secret_key
                else None
            )
            return {
                "yookassa_shop_id": settings_obj.yookassa_shop_id,
                "yookassa_secret_key_masked": _mask_secret_key(secret),
                "yookassa_enabled": settings_obj.yookassa_enabled,
            }

    @staticmethod
    async def get_yookassa_credentials() -> tuple[str, str] | None:
        """Возвращает (shop_id, secret) для ЮKassa: сначала из БД, затем из env."""
        async with async_session() as session:
            settings_obj = await session.get(PlatformSettings, 1)
            if settings_obj is not None:
                shop_id = settings_obj.yookassa_shop_id
                secret = (
                    decrypt(settings_obj.yookassa_secret_key)
                    if settings_obj.yookassa_secret_key
                    else None
                )
                if shop_id and secret:
                    return (shop_id, secret)

        if settings.yookassa_shop_id and settings.yookassa_secret_key:
            return (settings.yookassa_shop_id, settings.yookassa_secret_key)

        return None

    @staticmethod
    async def is_yookassa_enabled() -> bool:
        """True, если в БД или env настроены оба ключа ЮKassa."""
        async with async_session() as session:
            settings_obj = await session.get(PlatformSettings, 1)
            if settings_obj is not None and settings_obj.yookassa_enabled:
                if settings_obj.yookassa_shop_id and settings_obj.yookassa_secret_key:
                    return True

        return settings.yookassa_enabled

    @staticmethod
    async def update_payment_settings(
        yookassa_shop_id: str | None = None,
        yookassa_secret_key: str | None = None,
        yookassa_enabled: bool | None = None,
    ) -> dict:
        """Обновляет настройки ЮKassa платформы."""
        async with async_session() as session:
            db_obj = await session.get(PlatformSettings, 1)
            if db_obj is None:
                db_obj = PlatformSettings(id=1)
                session.add(db_obj)

            if yookassa_shop_id is not None:
                db_obj.yookassa_shop_id = yookassa_shop_id or None

            if yookassa_secret_key is not None:
                db_obj.yookassa_secret_key = (
                    encrypt(yookassa_secret_key) if yookassa_secret_key else None
                )

            if yookassa_enabled is not None:
                db_obj.yookassa_enabled = yookassa_enabled

            await session.commit()
            await session.refresh(db_obj)

        return await PlatformSettingsService.get_settings()
