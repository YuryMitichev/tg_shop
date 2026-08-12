from aiogram import Router
from app.bot.shop_context import get_shop_id
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, MenuButtonWebApp, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.main_menu import get_reply_keyboard
from app.bot.states.order import ReviewState
from app.bot.utils.messages import track_message
from app.core.config import settings
from app.services.catalog_service import CatalogService
from app.services.message_service import MessageService
from app.services.order_service import OrderService
from app.services.shop_service import ShopService


def setup_router() -> Router:
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext, command: CommandObject):
        payload = command.args

        if payload and payload.startswith("review_"):
            product_id = _parse_id(payload, "review_")
            if product_id:
                await _start_review(message, state, product_id)
                return

        if payload and payload.startswith("manager_"):
            product_id = _parse_id(payload, "manager_")
            if product_id:
                await _contact_manager(message, product_id)
                return

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

    def _parse_id(payload: str, prefix: str) -> int | None:
        try:
            return int(payload[len(prefix):])
        except (ValueError, IndexError):
            return None

    async def _start_review(message: Message, state: FSMContext, product_id: int):
        shop_id = get_shop_id()
        has_bought = await OrderService.has_purchased(shop_id, message.from_user.id, product_id)

        if not has_bought:
            await message.answer("⭐ Отзывы доступны только после покупки товара.")
            return

        await state.update_data(product_id=product_id)
        await state.set_state(ReviewState.waiting_rating)

        builder = InlineKeyboardBuilder()
        for i in range(1, 6):
            builder.button(text="⭐" * i, callback_data=f"rate:{i}")
        builder.button(text="⬅ Отмена", callback_data="review_cancel")
        builder.adjust(5, 1)

        await message.answer(
            "⭐ <b>Оцените товар</b>\n\nВыберите оценку:",
            reply_markup=builder.as_markup(),
        )

    async def _contact_manager(message: Message, product_id: int):
        shop_id = get_shop_id()
        shop = await ShopService.get(shop_id)
        if not shop:
            await message.answer("Магазин недоступен.")
            return

        user = message.from_user
        user_link = f"@{user.username}" if user.username else user.full_name

        product = await CatalogService.get_product(shop_id, product_id)

        if product:
            product_line = f"📦 <b>{product['name']}</b> (ID: <code>{product['id']}</code>)"
        else:
            product_line = "📦 Информация о товаре недоступна"

        admin_text = (
            "💬 <b>Запрос консультации по товару</b>\n\n"
            f"Покупатель: {user_link} (ID: <code>{user.id}</code>)\n"
            f"{product_line}"
        )

        try:
            await message.bot.send_message(
                chat_id=shop["owner_telegram_id"],
                text=admin_text,
            )
        except Exception:
            await message.answer("❌ Не удалось связаться с менеджером. Попробуйте позже.")
            return

        builder = InlineKeyboardBuilder()
        builder.button(
            text="💬 Написать напрямую",
            url=f"tg://user?id={shop['owner_telegram_id']}",
        )

        await message.answer(
            "✅ Менеджер получил ваш запрос и скоро свяжется с вами.\n"
            "Вы также можете написать ему напрямую:",
            reply_markup=builder.as_markup(),
        )

    return router
