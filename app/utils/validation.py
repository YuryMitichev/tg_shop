import re

MAX_NAME_LENGTH = 100
MAX_PHONE_LENGTH = 30
MAX_ADDRESS_LENGTH = 300
MAX_COMMENT_LENGTH = 500
MAX_PRODUCT_NAME_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000


def validate_phone(text: str) -> bool:
    """Простейшая проверка: 10–15 цифр."""
    digits = re.sub(r"\D", "", text)
    return 10 <= len(digits) <= 15


def validate_name(text: str) -> bool:
    return 2 <= len(text.strip()) <= MAX_NAME_LENGTH


def validate_address(text: str) -> bool:
    return 5 <= len(text.strip()) <= MAX_ADDRESS_LENGTH


def validate_comment(text: str) -> bool:
    return len(text.strip()) <= MAX_COMMENT_LENGTH
