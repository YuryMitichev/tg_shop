from aiogram import Router
from app.bot.shop_context import get_shop_id
from aiogram.filters import CommandStart
from aiogram.types import Message, MenuButtonWebApp, WebAppInfo
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.main_menu import get_reply_keyboard
from app.bot.utils.messages import track_message
from app.core.config import settings
from app.services.message_service import MessageService


def setup_router() -> Router:
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext):

        await state.clear()

        if settings.webapp_enabled:
            await message.bot.set_chat_menu_button(
                chat_id=message.chat.id,
                menu_button=MenuButtonWebApp(
                    text="🏪 Витрина",
                    web_app=WebAppInfo(url=settings.webapp_url),
                ),
            )

        text = await MessageService.get(1, "welcome")

        msg = await message.answer(
            text=text,
            reply_markup=get_reply_keyboard(),
        )

        await track_message(state, msg)

    return router
