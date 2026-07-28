from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.utils.order_status import STATUS_LABELS


def get_user_orders_keyboard(orders: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for order in orders:
        label = STATUS_LABELS.get(order["status"], order["status"])
        builder.button(
            text=f"№{order['id']} — {label} — {order['total_amount']} ₽",
            callback_data=f"user_order:{order['id']}",
        )

    builder.button(text="⬅ Главное меню", callback_data="menu")

    builder.adjust(1)

    return builder.as_markup()


def get_user_order_back_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="⬅ К заказам", callback_data="my_orders")

    return builder.as_markup()
