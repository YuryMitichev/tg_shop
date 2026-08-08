from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.bot.shop_context import _shop_id_ctx


class ShopMiddleware(BaseMiddleware):
    """Устанавливает shop_id из экземпляра бота в contextvar."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot = data.get("bot")
        shop_id = getattr(bot, "shop_id", 1)

        token = _shop_id_ctx.set(shop_id)
        try:
            return await handler(event, data)
        finally:
            _shop_id_ctx.reset(token)
