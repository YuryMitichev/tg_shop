import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select

from app.bot.bot import get_bot
from app.core.config import settings
from app.database.db import async_session
from app.models.admin_user import AdminUser


class AdminAuthService:
    """
    Авторизация админ-панели через одноразовый код из Telegram.

    Flow:
    1. POST /request-code → бот присылает 6-значный код (живёт 5 мин)
    2. POST /verify → проверка кода, выдача JWT (живёт 24 часа)

    JWT содержит shop_id — к какому магазину у админа доступ.
    """

    _codes: dict[int, tuple[str, float, int, bool]] = {}

    CODE_TTL = 300
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRES = timedelta(hours=24)

    @staticmethod
    async def _resolve_shop_id(telegram_user_id: int) -> tuple[int, bool] | None:
        """Определяет shop_id и флаг супер-админа для пользователя.

        Возвращает (shop_id, is_super_admin) или None.
        """
        if telegram_user_id in settings.super_admin_id_list:
            return (1, True)

        if telegram_user_id in settings.admin_id_list:
            return (1, False)

        async with async_session() as session:
            result = await session.execute(
                select(AdminUser).where(AdminUser.telegram_user_id == telegram_user_id)
            )
            admin = result.scalar_one_or_none()
            if admin:
                return (admin.shop_id, False)

        return None

    @staticmethod
    async def request_code(telegram_user_id: int) -> bool:
        resolved = await AdminAuthService._resolve_shop_id(telegram_user_id)
        if resolved is None:
            return False

        shop_id, is_super = resolved

        code = f"{secrets.randbelow(1000000):06d}"
        AdminAuthService._codes[telegram_user_id] = (code, time.time() + AdminAuthService.CODE_TTL, shop_id, is_super)

        bot = get_bot()
        if bot is None:
            return False

        await bot.send_message(
            telegram_user_id,
            f"🔐 <b>Код входа в админ-панель</b>\n\n"
            f"<code>{code}</code>\n\n"
            f"Действует 5 минут.",
        )
        return True

    @staticmethod
    def verify_code(telegram_user_id: int, code: str) -> str | None:
        stored = AdminAuthService._codes.get(telegram_user_id)

        if stored is None:
            return None

        stored_code, expires, shop_id, is_super = stored

        if time.time() > expires:
            AdminAuthService._codes.pop(telegram_user_id, None)
            return None

        if stored_code != code.strip():
            return None

        AdminAuthService._codes.pop(telegram_user_id, None)

        return AdminAuthService._create_token(telegram_user_id, shop_id, is_super)

    @staticmethod
    def _create_token(telegram_user_id: int, shop_id: int = 1, is_super_admin: bool = False) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(telegram_user_id),
            "shop_id": shop_id,
            "super_admin": is_super_admin,
            "iat": now,
            "exp": now + AdminAuthService.JWT_EXPIRES,
        }
        return jwt.encode(payload, settings.resolved_jwt_secret, algorithm=AdminAuthService.JWT_ALGORITHM)

    @staticmethod
    async def verify_token(token: str) -> dict | None:
        """Возвращает {'admin_id': int, 'shop_id': int, 'is_super_admin': bool} или None."""
        try:
            payload = jwt.decode(
                token,
                settings.resolved_jwt_secret,
                algorithms=[AdminAuthService.JWT_ALGORITHM],
            )
            admin_id = int(payload["sub"])
            shop_id = int(payload.get("shop_id", 1))
            is_super = bool(payload.get("super_admin", False))

            if not is_super:
                from app.services.admin_user_service import AdminUserService
                if not await AdminUserService.is_admin(shop_id, admin_id):
                    return None

            return {"admin_id": admin_id, "shop_id": shop_id, "is_super_admin": is_super}
        except Exception:
            return None
