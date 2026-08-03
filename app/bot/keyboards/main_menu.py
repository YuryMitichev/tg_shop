from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.config import settings


REPLY_BUTTONS = ["🚚 Доставка"]


def get_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Постоянная клавиатура внизу экрана.
    WebApp-кнопка устанавливается отдельно через MenuButtonWebApp.
    """

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🚚 Доставка"),
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
