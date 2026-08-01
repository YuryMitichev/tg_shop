from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.services.admin_user_service import AdminUserService


class IsAdmin(BaseFilter):
    async def __call__(self, obj: TelegramObject) -> bool:
        if obj.from_user is None:
            return False
        return await AdminUserService.is_admin(1, obj.from_user.id)
