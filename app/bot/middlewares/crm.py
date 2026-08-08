from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot.shop_context import get_shop_id
from app.services.crm_service import CrmService


class CrmMiddleware(BaseMiddleware):
    """Логирует входящие сообщения и обновляет профиль пользователя."""

    async def __call__(
        self,
        handler,
        event: TelegramObject,
        data: dict,
    ):
        user = None
        if isinstance(event, Message):
            user = event.from_user
            text = event.text or event.caption
            msg_type = "text" if event.text else ("photo" if event.photo else "other")
            if user:
                shop_id = get_shop_id()
                await CrmService.get_or_create_profile(
                    shop_id,
                    telegram_user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                )
                await CrmService.update_last_seen(shop_id, user.id)
                await CrmService.log_message(
                    shop_id,
                    telegram_user_id=user.id,
                    direction="in",
                    message_type=msg_type,
                    text=text,
                )
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            if user:
                shop_id = get_shop_id()
                await CrmService.update_last_seen(shop_id, user.id)
                await CrmService.log_message(
                    shop_id,
                    telegram_user_id=user.id,
                    direction="in",
                    message_type="callback",
                    text=event.data,
                )

        return await handler(event, data)
