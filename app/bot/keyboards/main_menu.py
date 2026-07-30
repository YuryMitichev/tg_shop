from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.config import settings


REPLY_BUTTONS = ["🏪 Витрина", "🚚 Доставка", "💳 Оплата", "🧾 Чек об оплате"]


def get_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Постоянная клавиатура внизу экрана.
    Если Mini App включён — добавляется кнопка «🏪 Витрина».
    """

    rows = []

    if settings.webapp_enabled:
        rows.append([
            KeyboardButton(
                text="🏪 Витрина",
                web_app=WebAppInfo(url=settings.webapp_url),
            ),
        ])

    rows.append([
        KeyboardButton(text="🚚 Доставка"),
        KeyboardButton(text="💳 Оплата"),
        KeyboardButton(text="🧾 Чек об оплате"),
    ])

    return ReplyKeyboardMarkup(
        keyboard=rows,
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
