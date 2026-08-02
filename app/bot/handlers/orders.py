from aiogram import Router, F
from app.bot.shop_context import get_shop_id
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.orders import (
    get_user_orders_keyboard,
    get_user_order_back_keyboard,
)
from app.bot.utils.messages import show_screen, replace_with_text
from app.services.order_service import OrderService
from app.utils.order_status import STATUS_LABELS
from app.utils.escape import esc

router = Router()

_EMPTY_KB = None

def _format_date(dt) -> str:
    if dt is None:
        return ""
    return dt.strftime("%d.%m.%Y %H:%M")

def _render_orders_list(orders: list[dict]) -> str:
    if not orders:
        return "📦 <b>Мои заказы</b>\n\nУ вас пока нет заказов."

    lines = ["📦 <b>Мои заказы</b>\n"]

    for order in orders:
        label = STATUS_LABELS.get(order["status"], order["status"])
        date = _format_date(order.get("created_at"))
        lines.append(
            f"№{order['id']} — {label} — {order['total_amount']} ₽"
            + (f"  ({date})" if date else "")
        )

    lines.append("\nНажмите на заказ, чтобы увидеть детали.")

    return "\n".join(lines)

def _render_order_detail(order: dict) -> str:
    label = STATUS_LABELS.get(order["status"], order["status"])
    date = _format_date(order.get("created_at"))

    lines = [f"📦 <b>Заказ №{order['id']}</b>\n"]

    if date:
        lines.append(f"📅 {date}\n")

    lines.append(f"Статус: {label}")

    lines.append(f"\n👤 {esc(order['full_name'])}")
    lines.append(f"📞 {esc(order['phone'])}")
    lines.append(f"📍 {esc(order['address'])}")

    if order.get("comment"):
        lines.append(f"💬 {esc(order['comment'])}")

    lines.append("")

    for item in order["items"]:
        subtotal = item["price"] * item["quantity"]
        lines.append(
            f"• {item['product_name']} ({item['variant_volume']}) "
            f"× {item['quantity']} — {subtotal} ₽"
        )

    lines.append(f"\n💰 Итого: <b>{order['total_amount']} ₽</b>")

    return "\n".join(lines)

@router.message(F.text == "📦 Мои заказы")
async def my_orders_message(message: Message, state: FSMContext):
    await state.clear()

    orders = await OrderService.get_user_orders(get_shop_id(), message.from_user.id)

    await show_screen(
        message,
        state,
        _render_orders_list(orders),
        reply_markup=get_user_orders_keyboard(orders),
    )

@router.callback_query(F.data == "my_orders")
async def my_orders_callback(callback: CallbackQuery, state: FSMContext):
    orders = await OrderService.get_user_orders(get_shop_id(), callback.from_user.id)

    await replace_with_text(
        callback.message,
        callback.bot,
        callback.message.chat.id,
        state,
        _render_orders_list(orders),
        reply_markup=get_user_orders_keyboard(orders),
    )

    await callback.answer()

@router.callback_query(F.data.startswith("user_order:"))
async def show_user_order(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split(":")[1])

    order = await OrderService.get_user_order(
        get_shop_id(),
        callback.from_user.id,
        order_id,
    )

    if order is None:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    await replace_with_text(
        callback.message,
        callback.bot,
        callback.message.chat.id,
        state,
        _render_order_detail(order),
        reply_markup=get_user_order_back_keyboard(),
    )

    await callback.answer()