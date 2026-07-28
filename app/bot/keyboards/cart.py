from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_cart_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for item in items:
        builder.button(
            text="➖",
            callback_data=f"cart_dec:{item['cart_item_id']}"
        )
        builder.button(
            text=str(item["quantity"]),
            callback_data="ignore"
        )
        builder.button(
            text="➕",
            callback_data=f"cart_inc:{item['cart_item_id']}"
        )
        builder.button(
            text="🗑",
            callback_data=f"cart_remove:{item['cart_item_id']}"
        )

        builder.adjust(4)

    if items:
        builder.button(
            text="✅ Оформить заказ",
            callback_data="checkout"
        )
        builder.adjust(1)

    builder.button(
        text="⬅ Главное меню",
        callback_data="menu"
    )

    builder.adjust(1)

    return builder.as_markup()
