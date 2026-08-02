from fastapi import Header, HTTPException

from app.services.admin_auth_service import AdminAuthService


async def require_admin(authorization: str = Header(...)) -> dict:
    """
    FastAPI dependency: проверяет JWT-токен администратора.
    Возвращает {'admin_id': int, 'shop_id': int, 'is_super_admin': bool}.
    """
    token = authorization.replace("Bearer ", "", 1)

    result = await AdminAuthService.verify_token(token)

    if result is None:
        raise HTTPException(status_code=401, detail="Не авторизован")

    return result


async def require_super_admin(authorization: str = Header(...)) -> dict:
    """
    FastAPI dependency: проверяет JWT-токен супер-админа.
    Возвращает {'admin_id': int, 'shop_id': int, 'is_super_admin': bool}.
    """
    token = authorization.replace("Bearer ", "", 1)

    result = await AdminAuthService.verify_token(token)

    if result is None:
        raise HTTPException(status_code=401, detail="Не авторизован")

    if not result.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Требуются права супер-админа")

    return result
