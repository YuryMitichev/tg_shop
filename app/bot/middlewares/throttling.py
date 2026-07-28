import time
from collections import defaultdict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    """Ограничивает частоту запросов от одного пользователя."""

    def __init__(self, rate_limit: float = 0.5):
        self.rate_limit = rate_limit
        self._last_call: dict[int, float] = defaultdict(float)

    async def __call__(
        self,
        handler,
        event: TelegramObject,
        data: dict,
    ):
        user_id = (
            event.from_user.id
            if hasattr(event, "from_user") and event.from_user
            else 0
        )

        now = time.monotonic()

        if now - self._last_call[user_id] < self.rate_limit:
            if isinstance(event, CallbackQuery):
                await event.answer()
            return

        self._last_call[user_id] = now
        return await handler(event, data)
