from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.filters.admin import IsAdmin
from app.bot.keyboards.admin import (
    get_admin_message_edit_keyboard,
    get_admin_messages_keyboard,
)
from app.bot.shop_context import get_shop_id
from app.bot.states.admin_product import AdminMessageState
from app.services.message_service import MessageService


def setup_messages_router() -> Router:
    router = Router()
    router.message.filter(IsAdmin())
    router.callback_query.filter(IsAdmin())

    @router.callback_query(F.data == "admin_messages")
    async def list_messages(callback: CallbackQuery, state: FSMContext):
        await state.clear()

        messages = await MessageService.get_all(get_shop_id())

        await callback.message.edit_text(
            "💬 <b>Системные сообщения</b>\n\n"
            "📄 — стандартный текст\n"
            "📝 — изменённый текст\n\n"
            "Выберите сообщение для редактирования:",
            reply_markup=get_admin_messages_keyboard(messages),
        )

        await callback.answer()

    @router.callback_query(F.data.startswith("admin_msg:"))
    async def edit_message_start(callback: CallbackQuery, state: FSMContext):
        key = callback.data.split(":", 1)[1]

        msg = await MessageService.get_one(get_shop_id(), key)

        if msg is None:
            await callback.answer("Сообщение не найдено.", show_alert=True)
            return

        await state.set_state(AdminMessageState.waiting_new_content)
        await state.update_data(msg_key=key)

        status = "стандартный" if msg["is_default"] else "изменённый"

        await callback.message.edit_text(
            f"✏️ <b>{msg['label']}</b>\n"
            f"Статус: {status}\n\n"
            f"Текущий текст:\n\n{msg['content']}\n\n"
            "Отправьте новый текст сообщения.\n"
            "Поддерживаются HTML-теги: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, <code>&lt;code&gt;</code>.",
            reply_markup=get_admin_message_edit_keyboard(key),
        )

        await callback.answer()

    @router.message(AdminMessageState.waiting_new_content)
    async def edit_message_save(message: Message, state: FSMContext):
        data = await state.get_data()
        key = data["msg_key"]

        await MessageService.update(get_shop_id(), key, message.text)
        await state.clear()

        messages = await MessageService.get_all(get_shop_id())

        await message.answer(
            "✅ Текст сообщения обновлён.\n\n"
            "💬 <b>Системные сообщения</b>\n\n"
            "📄 — стандартный текст\n"
            "📝 — изменённый текст\n\n"
            "Выберите сообщение для редактирования:",
            reply_markup=get_admin_messages_keyboard(messages),
        )

    @router.callback_query(F.data.startswith("admin_msg_reset:"))
    async def reset_message(callback: CallbackQuery, state: FSMContext):
        key = callback.data.split(":", 1)[1]

        await MessageService.reset(get_shop_id(), key)
        await state.clear()

        msg = await MessageService.get_one(get_shop_id(), key)

        if msg is None:
            await callback.answer("Сообщение не найдено.", show_alert=True)
            return

        messages = await MessageService.get_all(get_shop_id())

        await callback.message.edit_text(
            f"✅ Сброшено к стандарту: <b>{msg['label']}</b>\n\n"
            "💬 <b>Системные сообщения</b>\n\n"
            "📄 — стандартный текст\n"
            "📝 — изменённый текст\n\n"
            "Выберите сообщение для редактирования:",
            reply_markup=get_admin_messages_keyboard(messages),
        )

        await callback.answer("Сброшено к стандарту")

    return router
