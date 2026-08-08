from aiogram import Router, F
from app.bot.shop_context import get_shop_id
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.utils.messages import show_screen, replace_with_text
from app.services.message_service import MessageService
from app.services.shop_service import ShopService


def setup_router() -> Router:
    router = Router()

    _EMPTY_KB = InlineKeyboardMarkup(inline_keyboard=[])

    def _back_keyboard():
        builder = InlineKeyboardBuilder()

        builder.button(
            text="⬅ Главное меню",
            callback_data="menu"
        )

        return builder.as_markup()

    @router.message(F.text == "🚚 Доставка")
    async def show_delivery_msg(message: Message, state: FSMContext):
        await state.clear()

        shop_id = get_shop_id()
        text = await MessageService.get(shop_id, "delivery")

        shop = await ShopService.get(shop_id)
        couriers = shop.get("courier_services", []) if shop else []
        if couriers:
            text += "\n\n🚚 <b>Курьерские службы:</b>\n" + "\n".join(f"• {c}" for c in couriers)

        await show_screen(
            message,
            state,
            text,
            reply_markup=_EMPTY_KB,
        )

    @router.message(F.text == "💳 Оплата")
    async def show_payment_msg(message: Message, state: FSMContext):
        await state.clear()

        await show_screen(
            message,
            state,
            await MessageService.get(get_shop_id(), "payment"),
            reply_markup=_EMPTY_KB,
        )

    @router.callback_query(F.data == "delivery")
    async def show_delivery_cb(callback: CallbackQuery, state: FSMContext):
        await replace_with_text(
            callback.message,
            callback.bot,
            callback.message.chat.id,
            state,
            await MessageService.get(get_shop_id(), "delivery"),
            reply_markup=_back_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data == "payment")
    async def show_payment_cb(callback: CallbackQuery, state: FSMContext):
        await replace_with_text(
            callback.message,
            callback.bot,
            callback.message.chat.id,
            state,
            await MessageService.get(get_shop_id(), "payment"),
            reply_markup=_back_keyboard(),
        )
        await callback.answer()

    return router
