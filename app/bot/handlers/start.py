from aiogram import Router
from app.bot.shop_context import get_shop_id
from aiogram.filters import CommandStart
from aiogram.types import Message, MenuButtonWebApp, WebAppInfo
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.main_menu import get_reply_keyboard
from app.bot.utils.messages import track_message
from app.core.config import settings
from app.services.message_service import MessageService
from app.services.shop_service import ShopService


def setup_router() -> Router:
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext):

        await state.clear()

        shop_id = get_shop_id()
        shop = await ShopService.get(shop_id)
        delivery_enabled = shop["delivery_enabled"] if shop else True

        if settings.webapp_enabled:
            webapp_url = f"{settings.webapp_url}?shop={shop_id}"
            await message.bot.set_chat_menu_button(
                chat_id=message.chat.id,
                menu_button=MenuButtonWebApp(
                    text="🏪 Витрина",
                    web_app=WebAppInfo(url=webapp_url),
                ),
            )

        text = await MessageService.get(shop_id, "welcome")

        msg = await message.answer(
            text=text,
            reply_markup=get_reply_keyboard(delivery_enabled),
        )

        await track_message(state, msg)

    return router
