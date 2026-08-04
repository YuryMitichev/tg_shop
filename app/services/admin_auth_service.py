import secrets
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import delete, select

from app.bot.bot import get_bot
from app.core.config import settings
from app.database.db import async_session
from app.models.admin_user import AdminUser
from app.models.login_token import LoginToken


class AdminAuthService:
    """
    Авторизация админ-панели через magic link из Telegram.

    Flow:
    1. POST /request-login → бот присылает ссылку с токеном (живёт 5 мин)
    2. Пользователь кликает → фронт вызывает /verify-token → выдача JWT (живёт 24 часа)

    Токен ссылки — 64 случайных символа (2^256 комбинаций),
    брутфорс математически невозможен.

    JWT содержит shop_id — к какому магазину у админа доступ.
    """

    LINK_TTL = 300
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
    async def request_login(telegram_user_id: int) -> bool:
        resolved = await AdminAuthService._resolve_shop_id(telegram_user_id)
        if resolved is None:
            return False

        shop_id, is_super = resolved

        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=AdminAuthService.LINK_TTL)

        async with async_session() as session:
            await session.execute(
                delete(LoginToken).where(LoginToken.expires_at < datetime.now(timezone.utc))
            )
            session.add(LoginToken(
                token=token,
                telegram_user_id=telegram_user_id,
                shop_id=shop_id,
                is_super_admin=is_super,
                expires_at=expires_at,
            ))
            await session.commit()

        bot = get_bot(shop_id)
        if bot is None:
            return False

        base_url = settings.admin_panel_url or "https://t.me"
        login_url = f"{base_url.rstrip('/')}/login?token={token}"

        await bot.send_message(
            telegram_user_id,
            f"🔐 <b>Вход в админ-панель</b>\n\n"
            f"Нажмите на ссылку для входа:\n\n{login_url}\n\n"
            f"Ссылка действует 5 минут.",
        )
        return True

    @staticmethod
    async def verify_login_token(token: str) -> str | None:
        async with async_session() as session:
            result = await session.execute(
                select(LoginToken).where(LoginToken.token == token)
            )
            login_token = result.scalar_one_or_none()

            if login_token is None:
                return None

            now = datetime.now(timezone.utc)
            if login_token.expires_at.tzinfo is None:
                login_token.expires_at = login_token.expires_at.replace(tzinfo=timezone.utc)

            if now > login_token.expires_at:
                await session.delete(login_token)
                await session.commit()
                return None

            payload_data = {
                "telegram_user_id": login_token.telegram_user_id,
                "shop_id": login_token.shop_id,
                "is_super": login_token.is_super_admin,
            }

            await session.delete(login_token)
            await session.commit()

        return AdminAuthService._create_token(
            payload_data["telegram_user_id"],
            payload_data["shop_id"],
            payload_data["is_super"],
        )

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
