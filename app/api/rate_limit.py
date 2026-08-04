import json
from urllib.parse import parse_qsl

from slowapi import Limiter
from slowapi.util import get_remote_address


def get_real_ip(request) -> str:
    """Возвращает реальный IP клиента за reverse proxy (Caddy)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


def _extract_telegram_user_id(request) -> str | None:
    """Извлекает telegram_user_id из Authorization: tma <init_data>.
    Без валидации подписи — для rate limit достаточно идентификации.
    """
    auth = request.headers.get("authorization", "")
    if not auth.startswith("tma "):
        return None
    init_data = auth[4:]
    try:
        params = dict(parse_qsl(init_data, keep_blank_values=True))
        user_data = json.loads(params.get("user", "{}"))
        tg_id = user_data.get("id")
        if tg_id is not None:
            return f"user:{params.get('shop_id', '1')}:{tg_id}"
    except Exception:
        pass
    return None


def user_or_ip_key(request) -> str:
    """Ключ для rate limit: по telegram_user_id если есть, иначе по IP."""
    user_key = _extract_telegram_user_id(request)
    if user_key:
        return user_key
    return f"ip:{get_real_ip(request)}"


limiter = Limiter(key_func=get_real_ip)
