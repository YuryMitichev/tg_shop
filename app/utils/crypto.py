import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.encryption_key.encode())
    return _fernet


def encrypt(plaintext: str) -> str:
    """Шифрует строку, возвращает Fernet-токен (str)."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str | None:
    """Расшифровывает Fernet-токен. Возвращает None при ошибке."""
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        logger.error("Не удалось расшифровать токен")
        return None


def token_hash(token: str) -> str:
    """SHA-256 хэш токена для поиска/уникальности."""
    return hashlib.sha256(token.encode()).hexdigest()


def mask_token(token: str) -> str:
    """Маскирует токен для отображения: 1234****:ABC****"""
    if ":" in token:
        bot_id, rest = token.split(":", 1)
        return f"{bot_id[:4]}****:{rest[:3]}****"
    return "****"
