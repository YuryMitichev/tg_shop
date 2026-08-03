import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    """Ограничивает частоту запросов от одного пользователя.

    Lazy-очистка: при каждом обращении удаляет истёкшие записи пользователя.
    Cap: при превышении MAX_ENTRIES делает полную очистку всех истёкших.
    """

    MAX_ENTRIES = 10000
    ENTRY_TTL = 60.0

    def __init__(self, rate_limit: float = 0.5):
        self.rate_limit = rate_limit
        self._last_call: dict[int, float] = {}

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

        last = self._last_call.get(user_id)

        if last is not None and now - last > self.ENTRY_TTL:
            del self._last_call[user_id]
            last = None

        if len(self._last_call) > self.MAX_ENTRIES:
            cutoff = now - self.ENTRY_TTL
            self._last_call = {
                k: v for k, v in self._last_call.items() if v > cutoff
            }

        if last is not None and now - last < self.rate_limit:
            if isinstance(event, CallbackQuery):
                await event.answer()
            return

        self._last_call[user_id] = now
        return await handler(event, data)
