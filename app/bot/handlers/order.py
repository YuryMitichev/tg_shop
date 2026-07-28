from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from app.bot.states.order import OrderState
from app.bot.keyboards.main_menu import get_reply_keyboard
from app.bot.utils.messages import show_screen, track_message
from app.services.cart_service import CartService
from app.services.order_service import OrderService
from app.core.config import settings
from app.utils.escape import esc
from app.utils.validation import (
    validate_name,
    validate_phone,
    validate_address,
    validate_comment,
)

router = Router()

_EMPTY_KB = InlineKeyboardMarkup(inline_keyboard=[])


def _render_order_items(items: list[dict]) -> str:
    lines = []

    for item in items:
        lines.append(
            f"• {item['product_name']} ({item['volume']}) "
            f"× {item['quantity']} — {item['subtotal']} ₽"
        )

    return "\n".join(lines)


@router.callback_query(F.data == "checkout")
async def start_checkout(callback: CallbackQuery, state: FSMContext):
    items = await CartService.get_items(callback.from_user.id)

    if not items:
        await callback.answer("Корзина пуста.", show_alert=True)
        return

    await state.set_state(OrderState.waiting_full_name)

    await callback.message.edit_text(
        "📝 <b>Оформление заказа</b>\n\n"
        "Как к вам обращаться? Напишите имя и фамилию.",
        reply_markup=_EMPTY_KB,
    )

    await callback.answer()


@router.message(OrderState.waiting_full_name)
async def process_full_name(message: Message, state: FSMContext):
    if not validate_name(message.text):
        await show_screen(
            message, state,
            "❌ Имя слишком короткое или длинное (2–100 символов). Попробуйте ещё раз.",
        )
        return

    await state.update_data(full_name=message.text.strip())
    await state.set_state(OrderState.waiting_phone)

    await show_screen(message, state, "📞 Укажите номер телефона для связи.")


@router.message(OrderState.waiting_phone)
async def process_phone(message: Message, state: FSMContext):
    if not validate_phone(message.text):
        await show_screen(
            message, state,
            "❌ Неверный формат телефона.\n"
            "Пример: +7 999 123-45-67",
        )
        return

    await state.update_data(phone=message.text.strip())
    await state.set_state(OrderState.waiting_address)

    await show_screen(message, state, "📍 Укажите адрес доставки.")


@router.message(OrderState.waiting_address)
async def process_address(message: Message, state: FSMContext):
    if not validate_address(message.text):
        await show_screen(
            message, state,
            "❌ Адрес слишком короткий или длинный (5–300 символов). Попробуйте ещё раз.",
        )
        return

    await state.update_data(address=message.text.strip())
    await state.set_state(OrderState.waiting_comment)

    await show_screen(
        message,
        state,
        "💬 Добавьте комментарий к заказу (пожелания, удобное время и т.д.).\n\n"
        "Отправьте «-», чтобы пропустить.",
    )


@router.message(OrderState.waiting_comment)
async def process_comment(message: Message, state: FSMContext):
    data = await state.get_data()

    text = message.text.strip()

    if text == "-":
        comment = None
    elif not validate_comment(text):
        await show_screen(
            message, state,
            "❌ Комментарий слишком длинный (до 500 символов). Попробуйте ещё раз.",
        )
        return
    else:
        comment = text

    order = await OrderService.create_order(
        telegram_user_id=message.from_user.id,
        full_name=data["full_name"],
        phone=data["phone"],
        address=data["address"],
        comment=comment,
    )

    await state.clear()

    if order is None:
        await show_screen(
            message, state,
            "Корзина оказалась пуста, заказ не создан.",
        )
        return

    await message.delete()

    new_msg = await message.bot.send_message(
        chat_id=message.chat.id,
        text=(
            f"✅ <b>Заказ №{order['order_id']} оформлен!</b>\n\n"
            f"{_render_order_items(order['items'])}\n\n"
            f"💰 Итого: <b>{order['total']} ₽</b>\n\n"
            "Оплата — переводом по СБП или на карту, реквизиты придёт "
            "менеджер. Мы свяжемся с вами в ближайшее время для подтверждения."
        ),
        reply_markup=get_reply_keyboard(),
    )

    await track_message(state, new_msg)

    if settings.manager_chat_id:
        try:
            comment_line = f"\n💬 {esc(comment)}" if comment else ""
            await message.bot.send_message(
                settings.manager_chat_id,
                f"🆕 <b>Новый заказ №{order['order_id']}</b>\n\n"
                f"👤 {esc(order['full_name'])}\n"
                f"📞 {esc(order['phone'])}\n"
                f"📍 {esc(order['address'])}{comment_line}\n\n"
                f"{_render_order_items(order['items'])}\n\n"
                f"💰 Итого: <b>{order['total']} ₽</b>"
            )
        except Exception:
            pass
