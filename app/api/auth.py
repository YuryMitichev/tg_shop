import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from app.core.config import settings


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Проверяет подпись Telegram WebApp initData.
    Возвращает словарь пользователя (id, first_name, ...) или None.
    """
    try:
        params = dict(parse_qsl(init_data, keep_blank_values=True))
        hash_value = params.pop("hash", None)

        if not hash_value:
            return None

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode(),
            hashlib.sha256,
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        if calculated_hash != hash_value:
            return None

        user_data = json.loads(params.get("user", "{}"))
        return user_data

    except Exception:
        return None


async def get_current_user(authorization: str = Header(...)) -> dict:
    """
    FastAPI dependency: извлекает пользователя из заголовка
    Authorization: tma <init_data>
    """
    init_data = authorization.replace("tma ", "", 1)

    user = validate_init_data(init_data, settings.bot_token)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid auth")

    return user


async def get_current_user_id(user: dict = None) -> int:
    """Извлекает telegram_user_id из пользователя."""
    return user["id"]
