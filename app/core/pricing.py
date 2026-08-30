from decimal import Decimal, ROUND_HALF_UP


TRIAL_DURATION_DAYS = 14

MONTHLY_PLAN_NAME = "Подписка — 1 месяц"
MONTHLY_DURATION_DAYS = 30
MONTHLY_PRICE_RUB = Decimal("1299.00")

THREE_MONTH_PLAN_NAME = "Подписка — 3 месяца"
THREE_MONTH_DURATION_DAYS = 90
THREE_MONTH_DISCOUNT_PERCENT = 10
THREE_MONTH_REGULAR_PRICE_RUB = MONTHLY_PRICE_RUB * 3
THREE_MONTH_PRICE_RUB = (
    THREE_MONTH_REGULAR_PRICE_RUB * Decimal("0.90")
).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

TRIAL_PLAN_NAME = f"Пробный период — {TRIAL_DURATION_DAYS} дней"

PLAN_FEATURES = [
    "Каталог товаров без лимита",
    "Заказы и корзина без лимита",
    "Админ-панель и мини-приложение",
    "CRM: профили клиентов",
    "Приём оплаты (СБП / карты)",
    "Промокоды",
    "Рассылки без лимита",
    "Авто-теги клиентов",
    "Персональные офферы",
    "Расширенная аналитика продаж",
    "Администраторы без лимита",
    "Приоритетная поддержка",
]

CANONICAL_SUBSCRIPTION_PLANS = [
    {
        "name": TRIAL_PLAN_NAME,
        "description": "Бесплатный пробный период — все возможности",
        "price": 0.0,
        "duration_days": TRIAL_DURATION_DAYS,
        "is_trial": True,
        "features": [],
    },
    {
        "name": MONTHLY_PLAN_NAME,
        "description": "Полный функционал магазина за 1 299 ₽ в месяц.",
        "price": float(MONTHLY_PRICE_RUB),
        "duration_days": MONTHLY_DURATION_DAYS,
        "is_trial": False,
        "features": PLAN_FEATURES,
    },
    {
        "name": THREE_MONTH_PLAN_NAME,
        "description": (
            "Оплата за 3 месяца со скидкой 10%: "
            "3 507,30 ₽ вместо 3 897 ₽."
        ),
        "price": float(THREE_MONTH_PRICE_RUB),
        "duration_days": THREE_MONTH_DURATION_DAYS,
        "is_trial": False,
        "features": PLAN_FEATURES,
    },
]

CANONICAL_PLAN_NAMES = frozenset(
    plan["name"] for plan in CANONICAL_SUBSCRIPTION_PLANS
)

CANONICAL_PAID_PLAN_KEYS = frozenset(
    {
        (MONTHLY_PLAN_NAME, MONTHLY_DURATION_DAYS, MONTHLY_PRICE_RUB),
        (THREE_MONTH_PLAN_NAME, THREE_MONTH_DURATION_DAYS, THREE_MONTH_PRICE_RUB),
    }
)


def is_canonical_paid_plan(
    *, name: str, duration_days: int, price: int | float | Decimal
) -> bool:
    normalized_price = Decimal(str(price)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return (name, duration_days, normalized_price) in CANONICAL_PAID_PLAN_KEYS


def format_rub(value: int | float | Decimal) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount == amount.to_integral():
        return f"{int(amount):,} ₽".replace(",", " ")
    integer, fraction = f"{amount:.2f}".split(".")
    integer = f"{int(integer):,}".replace(",", " ")
    return f"{integer},{fraction} ₽"
