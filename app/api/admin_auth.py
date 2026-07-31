from fastapi import Header, HTTPException

from app.services.admin_auth_service import AdminAuthService


async def require_admin(authorization: str = Header(...)) -> int:
    """
    FastAPI dependency: проверяет JWT-токен администратора.
    Возвращает telegram_user_id.
    """
    token = authorization.replace("Bearer ", "", 1)

    user_id = AdminAuthService.verify_token(token)

    if user_id is None:
        raise HTTPException(status_code=401, detail="Не авторизован")

    return user_id
