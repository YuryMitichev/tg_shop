from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from app.bot.states.order import OrderState
from app.bot.keyboards.main_menu import get_reply_keyboard, get_cancel_reply_keyboard
from app.bot.utils.messages import show_screen, track_message
from app.services.order_service import OrderService
from app.core.config import settings
from app.utils.escape import esc

router = Router()

SHOP_ID = 1

_EMPTY_KB = InlineKeyboardMarkup(inline_keyboard=[])


@router.message(F.text == "🧾 Чек об оплате")
async def start_receipt(message: Message, state: FSMContext):
    """Начало отправки чека — запрос номера заказа."""
    await state.set_state(OrderState.waiting_receipt_order_id)

    await show_screen(
        message,
        state,
        "🧾 <b>Отправка чека об оплате</b>\n\n"
        "Введите номер заказа (цифры).\n"
        "Например: <code>42</code>",
        reply_markup=get_cancel_reply_keyboard(),
    )


@router.message(OrderState.waiting_receipt_order_id, F.text)
async def process_receipt_order_id(message: Message, state: FSMContext):
    """Проверка номера заказа."""
    text = message.text.strip()

    if text == "❌ Отмена":
        await state.clear()
        await show_screen(
            message,
            state,
            "Действие отменено.",
            reply_markup=get_reply_keyboard(),
        )
        return

    if not text.isdigit():
        await show_screen(
            message,
            state,
            "❌ Номер заказа — это число. Попробуйте ещё раз.",
        )
        return

    order_id = int(text)

    order = await OrderService.get_user_order(SHOP_ID, message.from_user.id, order_id)

    if order is None:
        await show_screen(
            message,
            state,
            f"❌ Заказ №{order_id} не найден.\nВведите правильный номер.",
        )
        return

    await state.update_data(order_id=order_id)
    await state.set_state(OrderState.waiting_receipt)

    await show_screen(
        message,
        state,
        f"Заказ №{order_id} найден.\n\n"
        "🧾 Отправьте фото чека об оплате одним сообщением.",
    )


@router.message(OrderState.waiting_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext):
    """Приём фото чека и пересылка менеджеру."""
    data = await state.get_data()
    order_id = data.get("order_id")

    await state.clear()

    await message.answer(
        "✅ Чек получен! Менеджер проверит оплату.\n"
        "Как только платёж подтвердится, вы получите уведомление.",
        reply_markup=get_reply_keyboard(),
    )

    if settings.manager_chat_id:
        try:
            order = await OrderService.get_user_order(SHOP_ID, message.from_user.id, order_id)

            if order:
                items_text = "\n".join(
                    f"• {item['product_name']} ({item['variant_volume']}) "
                    f"× {item['quantity']}"
                    for item in order["items"]
                )

                await message.bot.send_photo(
                    settings.manager_chat_id,
                    photo=message.photo[-1].file_id,
                    caption=(
                        f"🧾 <b>Чек по заказу №{order_id}</b>\n\n"
                        f"👤 {esc(order['full_name'])}\n"
                        f"📞 {esc(order['phone'])}\n\n"
                        f"{items_text}\n\n"
                        f"💰 Итого: <b>{order['total_amount']} ₽</b>\n\n"
                        "Проверьте оплату и смените статус в /admin"
                    ),
                )
        except Exception:
            pass
