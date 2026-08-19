import re
from dataclasses import asdict, dataclass


PREFILTER_VERSION = "rules-1.0"


@dataclass(frozen=True)
class PrefilterDecision:
    label: str
    confidence: float
    features: dict
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


_PRICE_RE = re.compile(
    r"(?:\b\d[\d\s]*(?:[.,]\d{1,2})?\s*(?:₽|руб(?:лей|ля|ль)?|р\.|€|\$|usd|eur)\b)"
    r"|(?:\b(?:цена|стоимость)\s*[:—-]?\s*\d)",
    re.IGNORECASE,
)
_SKU_RE = re.compile(r"\b(?:артикул|арт\.?|sku)\s*[:№#-]?\s*[a-zа-я0-9_-]+", re.IGNORECASE)
_SIZE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:мл|л|мг|г|кг|см|мм|м|шт|размер(?:а|ов)?|xs|s|m|l|xl|xxl)\b",
    re.IGNORECASE,
)

_PRODUCT_WORDS = (
    "в наличии",
    "заказать",
    "доставка",
    "оформить заказ",
    "характеристик",
    "состав",
    "материал",
    "цвет",
    "объем",
    "объём",
    "размер",
    "модель",
    "коллекция",
)

_NON_PRODUCT_PATTERNS = (
    re.compile(r"\bпоздравля(?:ем|ю)|с праздником|доброе утро\b", re.IGNORECASE),
    re.compile(r"\bваканси(?:я|и)|ищем сотрудник|требуется\b", re.IGNORECASE),
    re.compile(r"\bрасписани(?:е|я)|режим работы|технические работы\b", re.IGNORECASE),
    re.compile(r"\bопрос|голосовани(?:е|я)\b", re.IGNORECASE),
    re.compile(r"\bконкурс|розыгрыш|победител(?:ь|я|и)\b", re.IGNORECASE),
    re.compile(r"\bновост(?:ь|и)|важная информация|организационн\w+\s+(?:вопрос|новост)\b", re.IGNORECASE),
)


def classify_post(text: str | None, *, has_photos: bool) -> PrefilterDecision:
    """Консервативный бесплатный фильтр перед LLM.

    Только очевидный нетоварный текст получает ``non_product``. Любое
    сомнение намеренно уходит в AI, а фото без подписи — владельцу.
    """
    clean = " ".join((text or "").split()).strip()
    if not clean:
        if has_photos:
            return PrefilterDecision(
                label="needs_manual",
                confidence=1.0,
                features={"has_photos": True, "empty_text": True},
                reason="У фотографий нет подписи: текстовый AI не сможет заполнить карточку.",
            )
        return PrefilterDecision(
            label="ambiguous",
            confidence=0.0,
            features={"has_photos": False, "empty_text": True},
            reason="Пустая публикация не отсекается автоматически.",
        )

    lowered = clean.casefold()
    price = bool(_PRICE_RE.search(clean))
    sku = bool(_SKU_RE.search(clean))
    size = bool(_SIZE_RE.search(clean))
    product_words = [word for word in _PRODUCT_WORDS if word in lowered]
    non_product = [pattern.pattern for pattern in _NON_PRODUCT_PATTERNS if pattern.search(clean)]
    product_score = int(price) * 3 + int(sku) * 2 + int(size) + min(len(product_words), 3)
    if has_photos and product_words:
        product_score += 1

    features = {
        "has_photos": has_photos,
        "price": price,
        "sku": sku,
        "size_or_volume": size,
        "product_words": product_words,
        "non_product_patterns": non_product,
        "product_score": product_score,
    }

    if non_product and product_score == 0:
        return PrefilterDecision(
            label="non_product",
            confidence=0.97 if len(non_product) > 1 else 0.95,
            features=features,
            reason="Есть явный нетоварный сценарий и нет ни одного товарного сигнала.",
        )
    if product_score >= 3:
        return PrefilterDecision(
            label="product",
            confidence=min(0.99, 0.72 + product_score * 0.04),
            features=features,
            reason="Обнаружены сильные товарные сигналы.",
        )
    return PrefilterDecision(
        label="ambiguous",
        confidence=0.5,
        features=features,
        reason="Недостаточно данных для безопасного локального решения.",
    )
