from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.utils.messages import show_screen, replace_with_text
from app.services.message_service import MessageService

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

    await show_screen(
        message,
        state,
        await MessageService.get("delivery"),
        reply_markup=_EMPTY_KB,
    )


@router.message(F.text == "💳 Оплата")
async def show_payment_msg(message: Message, state: FSMContext):
    await state.clear()

    await show_screen(
        message,
        state,
        await MessageService.get("payment"),
        reply_markup=_EMPTY_KB,
    )


@router.callback_query(F.data == "delivery")
async def show_delivery_cb(callback: CallbackQuery, state: FSMContext):
    await replace_with_text(
        callback.message,
        callback.bot,
        callback.message.chat.id,
        state,
        await MessageService.get("delivery"),
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
        await MessageService.get("payment"),
        reply_markup=_back_keyboard(),
    )
    await callback.answer()
