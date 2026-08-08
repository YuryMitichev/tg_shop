from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.bot.shop_context import get_shop_id
from app.services.admin_user_service import AdminUserService


class IsAdmin(BaseFilter):
    async def __call__(self, obj: TelegramObject) -> bool:
        if obj.from_user is None:
            return False
        return await AdminUserService.is_admin(get_shop_id(), obj.from_user.id)
