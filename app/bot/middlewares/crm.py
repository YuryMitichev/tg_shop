from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

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
                await CrmService.get_or_create_profile(
                    telegram_user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                )
                await CrmService.update_last_seen(user.id)
                await CrmService.log_message(
                    telegram_user_id=user.id,
                    direction="in",
                    message_type=msg_type,
                    text=text,
                )
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            if user:
                await CrmService.update_last_seen(user.id)
                await CrmService.log_message(
                    telegram_user_id=user.id,
                    direction="in",
                    message_type="callback",
                    text=event.data,
                )

        return await handler(event, data)
