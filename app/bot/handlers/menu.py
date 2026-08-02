from aiogram import F, Router
from app.bot.shop_context import get_shop_id
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from app.bot.utils.messages import replace_with_text
from app.services.message_service import MessageService


def setup_router() -> Router:
    router = Router()

    _EMPTY_KB = InlineKeyboardMarkup(inline_keyboard=[])

    @router.callback_query(F.data == "menu")
    async def menu_callback(callback: CallbackQuery, state: FSMContext):

        await state.clear()

        text = await MessageService.get(1, "menu")

        await replace_with_text(
            callback.message,
            callback.bot,
            callback.message.chat.id,
            state,
            text,
            reply_markup=_EMPTY_KB,
        )

        await callback.answer()

    return router
