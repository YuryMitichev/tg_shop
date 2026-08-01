from sqlalchemy import select

from app.core.config import settings
from app.database.db import async_session
from app.models.admin_user import AdminUser


class AdminUserService:
    @staticmethod
    async def is_admin(telegram_user_id: int) -> bool:
        if telegram_user_id in settings.admin_id_list:
            return True

        async with async_session() as session:
            result = await session.execute(
                select(AdminUser).where(AdminUser.telegram_user_id == telegram_user_id)
            )
            return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_all() -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(AdminUser).order_by(AdminUser.created_at)
            )
            admins = result.scalars().all()

            db_ids = {a.telegram_user_id for a in admins}

            env_admins = [
                {
                    "id": -uid,
                    "telegram_user_id": uid,
                    "display_name": "Супер-админ (env)",
                    "created_at": None,
                    "is_super": True,
                }
                for uid in settings.admin_id_list
                if uid not in db_ids
            ]

            db_admins = [
                {
                    "id": a.id,
                    "telegram_user_id": a.telegram_user_id,
                    "display_name": a.display_name,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "is_super": False,
                }
                for a in admins
            ]

            return env_admins + db_admins

    @staticmethod
    async def add(telegram_user_id: int, display_name: str | None = None) -> int:
        async with async_session() as session:
            admin = AdminUser(
                telegram_user_id=telegram_user_id,
                display_name=display_name,
            )
            session.add(admin)
            await session.commit()
            return admin.id

    @staticmethod
    async def delete(admin_id: int) -> bool:
        async with async_session() as session:
            admin = await session.get(AdminUser, admin_id)
            if admin is None:
                return False
            await session.delete(admin)
            await session.commit()
            return True
