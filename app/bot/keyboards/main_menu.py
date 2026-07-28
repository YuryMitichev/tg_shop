from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


REPLY_BUTTONS = ["🛍 Каталог", "🛒 Корзина", "🚚 Доставка", "💳 Оплата"]


def get_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Постоянная клавиатура внизу экрана.
    """

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛍 Каталог"),
                KeyboardButton(text="🛒 Корзина"),
            ],
            [
                KeyboardButton(text="📦 Мои заказы"),
                KeyboardButton(text="🚚 Доставка"),
                KeyboardButton(text="💳 Оплата"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def get_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


def get_back_to_menu_inline() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="⬅ Главное меню", callback_data="menu")

    return builder.as_markup()
