from aiogram import Router, F
from app.bot.shop_context import get_shop_id
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, MenuButtonWebApp, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.main_menu import get_reply_keyboard
from app.bot.utils.messages import track_message
from app.core.config import settings
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_user_service import AdminUserService
from app.services.message_service import MessageService
from app.services.shop_service import ShopService


def setup_router() -> Router:
    router = Router()

    @router.message(Command("admin"))
    async def cmd_admin(message: Message):
        shop_id = get_shop_id()
        is_admin = await AdminUserService.is_admin(shop_id, message.from_user.id)

        if not is_admin:
            await message.answer(
                "Извините, но Вы не является администратором этого магазина"
            )
            return

        login_url = await AdminAuthService.create_login_url(
            message.from_user.id, shop_id
        )
        if login_url is None:
            admin_url = settings.admin_panel_url
            login_url = f"{admin_url.rstrip('/')}/login" if admin_url else None

        if login_url is None:
            await message.answer("⚙️ Админ-панель недоступна.")
            return

        await message.answer(
            "⚙️ <b>Панель администратора</b>\n\n"
            "Управляйте товарами, заказами, промокодами и статистикой "
            "в удобной веб-админ-панели 👇",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📊 Открыть админ-панель", url=login_url)]
                ]
            ),
        )

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext, command: CommandObject):
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
