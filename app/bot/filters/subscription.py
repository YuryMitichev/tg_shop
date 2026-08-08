from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot.shop_context import get_shop_id
from app.services.subscription_service import SubscriptionService


class SubscriptionActive(BaseFilter):
    """Aiogram-фильтр: пропускает обработчик только при активной подписке.

    При истёкшей подписке показывает предупреждение и возвращает False,
    блокируя выполнение хендлера. Заказы и CRM (в роутах без этого фильтра)
    остаются доступны всегда.
    """

    _BLOCKED_MSG = "⛔ Подписка истекла. Доступны только заказы и клиенты."

    async def __call__(self, obj: TelegramObject) -> bool:
        if await SubscriptionService.is_shop_active(get_shop_id()):
            return True

        if isinstance(obj, CallbackQuery):
            await obj.answer(text=self._BLOCKED_MSG, show_alert=True)
        elif isinstance(obj, Message):
            await obj.answer(text=self._BLOCKED_MSG)

        return False
