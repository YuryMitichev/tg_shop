from slowapi import Limiter
from slowapi.util import get_remote_address


def get_real_ip(request) -> str:
    """Возвращает реальный IP клиента за reverse proxy (Caddy)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=get_real_ip)
