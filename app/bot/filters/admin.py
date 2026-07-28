from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.core.config import settings


class IsAdmin(BaseFilter):
    async def __call__(self, obj: TelegramObject) -> bool:
        return (
            bool(settings.admin_id_list)
            and obj.from_user is not None
            and obj.from_user.id in settings.admin_id_list
        )
