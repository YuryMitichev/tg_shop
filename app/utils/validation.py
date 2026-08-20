import re
import unicodedata

MAX_NAME_LENGTH = 100
MAX_PHONE_LENGTH = 30
MAX_ADDRESS_LENGTH = 300
MAX_COMMENT_LENGTH = 500
MAX_PRODUCT_NAME_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000
MAX_CATEGORY_NAME_LENGTH = 100
MAX_CATEGORY_EMOJI_LENGTH = 16


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


def normalize_category_emoji(value: str | None) -> str | None:
    """Accept only a short Unicode symbol/emoji sequence, never markup or text."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > MAX_CATEGORY_EMOJI_LENGTH:
        raise ValueError("Эмодзи категории слишком длинный")

    has_symbol = False
    for char in value:
        codepoint = ord(char)
        category = unicodedata.category(char)
        if category in {"So", "Sk"} or 0x1F1E6 <= codepoint <= 0x1F1FF:
            has_symbol = True
            continue
        if category == "Mn" or codepoint in {0x200D, 0xFE0F, 0x20E3}:
            continue
        raise ValueError("Поле категории допускает только Unicode-эмодзи")

    if not has_symbol:
        raise ValueError("Укажите Unicode-эмодзи")
    return value
