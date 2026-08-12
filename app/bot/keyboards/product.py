from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_product_keyboard(product: dict, selected_variant_id: int, position: int, total: int) -> InlineKeyboardMarkup:
    """
    Клавиатура карточки товара.

    Структура:
      [вариант1] [вариант2] [вариант3]     ← выбор объёма
      [        🛒 Добавить в корзину      ]  ← одна кнопка
      [        ⭐ Оставить отзыв           ]  ← одна кнопка
      [        💬 Написать менеджеру       ]  ← одна кнопка
      [◀️]              [1/3]           [▶️]  ← навигация
      [        ⬅️ Категории               ]  ← назад
    """

    builder = InlineKeyboardBuilder()

    # Выбор варианта (кнопки в один ряд)
    for variant in product["variants"]:
        text = variant["volume"]
        if variant["id"] == selected_variant_id:
            text = f"✅ {text}"
        builder.button(text=text, callback_data=f"variant:{variant['id']}")

    # Добавить в корзину
    builder.button(text="🛒 Добавить в корзину", callback_data="add_to_cart")

    # Отзыв
    builder.button(text="⭐ Оставить отзыв", callback_data="review")

    # Написать менеджеру
    builder.button(text="💬 Написать менеджеру", callback_data="contact_manager")

    # Навигация
    builder.button(text="◀️", callback_data="prev_product")
    builder.button(text=f"{position}/{total}", callback_data="ignore")
    builder.button(text="▶️", callback_data="next_product")

    # Назад к категориям
    builder.button(text="⬅️ Категории", callback_data="catalog")

    # Раскладка: ряд 1 — варианты, ряд 2 — корзина, ряд 3 — отзыв, ряд 4 — менеджер, ряд 5 — навигация (3), ряд 6 — назад
    builder.adjust(len(product["variants"]), 1, 1, 1, 3, 1)

    return builder.as_markup()
