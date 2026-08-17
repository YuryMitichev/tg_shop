import secrets
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import delete, select

from app.bot.bot import get_bot
from app.core.cache import TTLCache
from app.core.config import settings
from app.database.db import async_session
from app.models.admin_user import AdminUser
from app.models.login_token import LoginToken


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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

    _token_cache: TTLCache = TTLCache(ttl=30)

    @staticmethod
    async def _resolve_shop_ids(telegram_user_id: int) -> list[tuple[int, bool]]:
        """Определяет список магазинов для пользователя.

        Приоритет: собственные магазины (AdminUser), затем — платформенный админ.
        Возвращает список (shop_id, is_super_admin).
        """
        is_super = telegram_user_id in settings.super_admin_id_list

        async with async_session() as session:
            result = await session.execute(
                select(AdminUser)
                .where(AdminUser.telegram_user_id == telegram_user_id)
                .order_by(AdminUser.created_at.desc())
            )
            admins = result.scalars().all()

        if admins:
            return [(a.shop_id, is_super) for a in admins]

        if is_super:
            return [(1, True)]

        if telegram_user_id in settings.admin_id_list:
            return [(1, False)]

        return []

    @staticmethod
    async def _create_login_token(
        telegram_user_id: int, shop_id: int, is_super_admin: bool,
    ) -> str:
        """Создаёт LoginToken и возвращает сырой токен."""
        async with async_session() as session:
            await session.execute(
                delete(LoginToken).where(LoginToken.expires_at < _utcnow())
            )
            await session.commit()

        token = secrets.token_urlsafe(48)
        expires_at = _utcnow() + timedelta(seconds=AdminAuthService.LINK_TTL)

        async with async_session() as session:
            session.add(LoginToken(
                token=token,
                telegram_user_id=telegram_user_id,
                shop_id=shop_id,
                is_super_admin=is_super_admin,
                expires_at=expires_at,
            ))
            await session.commit()

        return token

    @staticmethod
    async def create_login_url(
        telegram_user_id: int, shop_id: int,
    ) -> str | None:
        """Создаёт magic link для конкретного магазина без отправки через бот.

        Возвращает готовый URL вида ``{base}/login?token=…`` или ``None``,
        если пользователь не является админом магазина.
        """
        from app.services.admin_user_service import AdminUserService

        if not await AdminUserService.is_admin(shop_id, telegram_user_id):
            return None

        is_super = telegram_user_id in settings.super_admin_id_list
        token = await AdminAuthService._create_login_token(
            telegram_user_id, shop_id, is_super,
        )
        base_url = settings.admin_panel_url or "https://t.me"
        return f"{base_url.rstrip('/')}/login?token={token}"

    @staticmethod
    async def request_login(
        telegram_user_id: int,
        shop_id: int | None = None,
        panel: str = "admin",
    ) -> bool:
        from app.services.shop_service import ShopService

        shops = await AdminAuthService._resolve_shop_ids(telegram_user_id)
        if not shops:
            return False

        if shop_id is not None:
            shops = [(sid, sup) for sid, sup in shops if sid == shop_id]
            if not shops:
                return False

        if panel == "platform":
            base_url = settings.platform_admin_url or settings.admin_panel_url or "https://t.me"
        else:
            base_url = settings.admin_panel_url or "https://t.me"

        sent_any = False
        for sid, is_super in shops:
            bot = get_bot(sid)
            if bot is None:
                continue

            token = await AdminAuthService._create_login_token(
                telegram_user_id, sid, is_super,
            )
            login_url = f"{base_url.rstrip('/')}/login?token={token}"

            shop = await ShopService.get(sid)
            shop_label = f" — «{shop['name']}»" if shop else ""

            await bot.send_message(
                telegram_user_id,
                f"🔐 <b>Вход в админ-панель</b>{shop_label}\n\n"
                f"Нажмите на ссылку для входа:\n\n{login_url}\n\n"
                f"Ссылка действует 5 минут.",
            )
            sent_any = True

        return sent_any

    @staticmethod
    async def verify_login_token(token: str) -> str | None:
        async with async_session() as session:
            result = await session.execute(
                select(LoginToken).where(LoginToken.token == token)
            )
            login_token = result.scalar_one_or_none()

            if login_token is None:
                return None

            now = _utcnow()
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
        hit, cached = AdminAuthService._token_cache.get(token)
        if hit:
            return cached

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

            result = {"admin_id": admin_id, "shop_id": shop_id, "is_super_admin": is_super}
            AdminAuthService._token_cache.set(token, result)
            return result
        except Exception:
            return None
