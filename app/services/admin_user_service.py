from sqlalchemy import select

from app.core.config import settings
from app.database.db import async_session
from app.models.admin_user import AdminUser


class AdminUserService:
    @staticmethod
    async def is_admin(shop_id: int, telegram_user_id: int) -> bool:
        if telegram_user_id in settings.admin_id_list:
            return True

        async with async_session() as session:
            result = await session.execute(
                select(AdminUser).where(
                    AdminUser.shop_id == shop_id,
                    AdminUser.telegram_user_id == telegram_user_id,
                )
            )
            return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_all(shop_id: int) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(AdminUser)
                .where(AdminUser.shop_id == shop_id)
                .order_by(AdminUser.created_at)
            )
            admins = result.scalars().all()

            return [
                {
                    "id": a.id,
                    "telegram_user_id": a.telegram_user_id,
                    "display_name": a.display_name,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "is_super": False,
                }
                for a in admins
            ]

    @staticmethod
    async def add(shop_id: int, telegram_user_id: int, display_name: str | None = None) -> int:
        async with async_session() as session:
            admin = AdminUser(
                shop_id=shop_id,
                telegram_user_id=telegram_user_id,
                display_name=display_name,
            )
            session.add(admin)
            await session.commit()
            return admin.id

    @staticmethod
    async def delete(shop_id: int, admin_id: int) -> bool:
        async with async_session() as session:
            admin = await session.get(AdminUser, admin_id)
            if admin is None or admin.shop_id != shop_id:
                return False
            await session.delete(admin)
            await session.commit()
            return True
