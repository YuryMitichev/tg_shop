from fastapi import Cookie, Depends, HTTPException, Request

from app.services.admin_auth_service import AdminAuthService
from app.services.subscription_service import SubscriptionService


class SubscriptionExpiredException(Exception):
    """Выбрасывается когда у магазина истекла подписка,
    а роут требует активной подписки."""
    pass


async def _extract_token(request: Request, admin_token: str | None = Cookie(default=None)) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:]
    return admin_token


async def require_admin(request: Request, admin_token: str | None = Cookie(default=None)) -> dict:
    """
    FastAPI dependency: проверяет JWT-токен из Authorization header или cookie.
    Возвращает {'admin_id': int, 'shop_id': int, 'is_super_admin': bool}.
    """
    token = await _extract_token(request, admin_token)
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизован")

    result = await AdminAuthService.verify_token(token)

    if result is None:
        raise HTTPException(status_code=401, detail="Не авторизован")

    return result


async def require_admin_full_access(admin: dict = Depends(require_admin)) -> dict:
    """
    То же что require_admin, но дополнительно проверяет статус подписки.
    Добавляет флаг 'subscription_active' (True/False) в возвращаемый dict.
    Не блокирует доступ — решение остаётся за роутами.
    """
    if admin.get("is_super_admin"):
        admin["subscription_active"] = True
        return admin

    admin["subscription_active"] = await SubscriptionService.is_shop_active(admin["shop_id"])
    return admin


async def require_active_subscription(
    admin: dict = Depends(require_admin_full_access),
) -> dict:
    """
    Зависимость для роутов, требующих активной подписки.
    Выбрасывает SubscriptionExpiredException (→ 403) если подписка истекла.
    Супер-админ всегда имеет доступ.
    """
    if not admin.get("subscription_active", True):
        raise SubscriptionExpiredException()
    return admin


async def require_super_admin(request: Request, admin_token: str | None = Cookie(default=None)) -> dict:
    """
    FastAPI dependency: проверяет JWT-токен супер-админа из header или cookie.
    Возвращает {'admin_id': int, 'shop_id': int, 'is_super_admin': bool}.
    """
    token = await _extract_token(request, admin_token)
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизован")

    result = await AdminAuthService.verify_token(token)

    if result is None:
        raise HTTPException(status_code=401, detail="Не авторизован")

    if not result.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Требуются права супер-админа")

    return result
