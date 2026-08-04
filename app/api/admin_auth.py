from fastapi import Cookie, HTTPException

from app.services.admin_auth_service import AdminAuthService


async def require_admin(admin_token: str | None = Cookie(default=None)) -> dict:
    """
    FastAPI dependency: проверяет JWT-токен из httpOnly-cookie.
    Возвращает {'admin_id': int, 'shop_id': int, 'is_super_admin': bool}.
    """
    if not admin_token:
        raise HTTPException(status_code=401, detail="Не авторизован")

    result = await AdminAuthService.verify_token(admin_token)

    if result is None:
        raise HTTPException(status_code=401, detail="Не авторизован")

    return result


async def require_super_admin(admin_token: str | None = Cookie(default=None)) -> dict:
    """
    FastAPI dependency: проверяет JWT-токен супер-админа из httpOnly-cookie.
    Возвращает {'admin_id': int, 'shop_id': int, 'is_super_admin': bool}.
    """
    if not admin_token:
        raise HTTPException(status_code=401, detail="Не авторизован")

    result = await AdminAuthService.verify_token(admin_token)

    if result is None:
        raise HTTPException(status_code=401, detail="Не авторизован")

    if not result.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Требуются права супер-админа")

    return result
