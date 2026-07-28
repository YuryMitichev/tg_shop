from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from app.bot.utils.messages import replace_with_text

router = Router()

_EMPTY_KB = InlineKeyboardMarkup(inline_keyboard=[])


@router.callback_query(F.data == "menu")
async def menu_callback(callback: CallbackQuery, state: FSMContext):

    await state.clear()

    await replace_with_text(
        callback.message,
        callback.bot,
        callback.message.chat.id,
        state,
        "👋 <b>Главное меню</b>\n\nВыберите раздел — кнопки внизу.",
        reply_markup=_EMPTY_KB,
    )

    await callback.answer()
