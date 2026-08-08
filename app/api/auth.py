import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from app.services.shop_service import ShopService

logger = logging.getLogger(__name__)


async def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Проверяет подпись Telegram WebApp initData.
    Возвращает словарь пользователя (id, first_name, ...) или None.
    """
    try:
        if not init_data:
            logger.warning("validate_init_data: empty init_data")
            return None

        params = dict(parse_qsl(init_data, keep_blank_values=True))
        hash_value = params.pop("hash", None)

        if not hash_value:
            logger.warning(
                "validate_init_data: no hash — keys=%s, len=%d",
                list(params.keys()),
                len(init_data),
            )
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
            logger.warning("validate_init_data: HMAC mismatch (wrong bot_token?)")
            return None

        user_data = json.loads(params.get("user", "{}"))
        return user_data

    except Exception as e:
        logger.warning("validate_init_data: exception %s", e)
        return None


async def _resolve_bot_token(shop_id: int | None) -> str | None:
    """Возвращает bot_token для магазина."""
    if shop_id is None:
        return None
    return await ShopService.get_bot_token(shop_id)


async def get_current_user(
    authorization: str = Header(...),
    x_shop_id: int | None = Header(None, alias="X-Shop-Id"),
) -> dict:
    """
    FastAPI dependency: извлекает пользователя из заголовка
    Authorization: tma <init_data>

    X-Shop-Id определяет, какой bot_token использовать для проверки.
    """
    init_data = authorization.replace("tma ", "", 1)

    bot_token = await _resolve_bot_token(x_shop_id)
    if bot_token is None:
        logger.warning("get_current_user: bot_token not found for shop_id=%s", x_shop_id)
        raise HTTPException(status_code=404, detail="Shop not found")

    user = await validate_init_data(init_data, bot_token)

    if not user:
        logger.warning(
            "get_current_user: auth failed — shop_id=%s, init_data_empty=%s, "
            "header_prefix_ok=%s, auth_preview=[%s]",
            x_shop_id,
            not init_data,
            authorization.startswith("tma "),
            authorization[:300],
        )
        raise HTTPException(status_code=401, detail="Invalid auth")

    user["shop_id"] = x_shop_id
    return user


async def get_optional_user(
    authorization: str | None = Header(None),
    x_shop_id: int | None = Header(None, alias="X-Shop-Id"),
) -> dict | None:
    """Опциональная авторизация — возвращает пользователя или None."""
    if not authorization:
        return None

    init_data = authorization.replace("tma ", "", 1)

    bot_token = await _resolve_bot_token(x_shop_id)
    if bot_token is None:
        return None

    user = await validate_init_data(init_data, bot_token)
    if user:
        user["shop_id"] = x_shop_id
    return user

