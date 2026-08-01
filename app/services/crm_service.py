from datetime import datetime

from sqlalchemy import select, func, or_

from app.database.db import async_session
from app.models.user_profile import UserProfile
from app.models.communication_log import CommunicationLog
from app.models.order import Order
from app.models.order_item import OrderItem


class CrmService:
    @staticmethod
    async def backfill_from_orders() -> int:
        """Создаёт профили для пользователей из заказов, у которых ещё нет профиля."""
        async with async_session() as session:
            tg_ids_result = await session.execute(
                select(Order.telegram_user_id)
                .where(Order.status != "cancelled")
                .distinct()
            )
            tg_ids = [r[0] for r in tg_ids_result.all()]

            count = 0
            for tg_id in tg_ids:
                existing = await session.get(UserProfile, tg_id)
                if existing is None:
                    last_order_result = await session.execute(
                        select(Order.full_name, Order.phone)
                        .where(Order.telegram_user_id == tg_id)
                        .order_by(Order.created_at.desc())
                        .limit(1)
                    )
                    last_order = last_order_result.one_or_none()

                    full_name = last_order[0] if last_order else ""
                    parts = full_name.split(" ", 1)
                    first_name = parts[0] if parts else full_name or None
                    last_name = parts[1] if len(parts) > 1 else None

                    profile = UserProfile(
                        telegram_user_id=tg_id,
                        first_name=first_name,
                        last_name=last_name,
                        phone=last_order[1] if last_order else None,
                    )
                    session.add(profile)
                    count += 1

            if count:
                await session.commit()
            return count

    @staticmethod
    async def get_or_create_profile(
        telegram_user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> UserProfile:
        async with async_session() as session:
            profile = await session.get(UserProfile, telegram_user_id)
            if profile is None:
                profile = UserProfile(
                    telegram_user_id=telegram_user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                )
                session.add(profile)
                await session.commit()
                await session.refresh(profile)
            else:
                changed = False
                if username and profile.username != username:
                    profile.username = username
                    changed = True
                if first_name and profile.first_name != first_name:
                    profile.first_name = first_name
                    changed = True
                if last_name and profile.last_name != last_name:
                    profile.last_name = last_name
                    changed = True
                if changed:
                    await session.commit()
            return profile

    @staticmethod
    async def update_last_seen(telegram_user_id: int) -> None:
        async with async_session() as session:
            profile = await session.get(UserProfile, telegram_user_id)
            if profile:
                profile.last_seen = datetime.now()
                await session.commit()

    @staticmethod
    async def log_message(
        telegram_user_id: int,
        direction: str = "in",
        message_type: str = "text",
        text: str | None = None,
        admin_id: int | None = None,
    ) -> None:
        truncated = text[:500] if text else None
        async with async_session() as session:
            log = CommunicationLog(
                telegram_user_id=telegram_user_id,
                direction=direction,
                message_type=message_type,
                text=truncated,
                admin_id=admin_id,
            )
            session.add(log)
            await session.commit()

    @staticmethod
    def _parse_tags(tags_str: str | None) -> list[str]:
        if not tags_str:
            return []
        return [t.strip() for t in tags_str.split(",") if t.strip()]

    @staticmethod
    def _profile_to_dict(profile: UserProfile, stats: dict | None = None) -> dict:
        data = {
            "telegram_user_id": profile.telegram_user_id,
            "username": profile.username,
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "full_name": " ".join(
                filter(None, [profile.first_name or "", profile.last_name or ""])
            ).strip(),
            "phone": profile.phone,
            "notes": profile.notes,
            "tags": CrmService._parse_tags(profile.tags),
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "last_seen": profile.last_seen.isoformat() if profile.last_seen else None,
        }
        if stats:
            data.update(stats)
        return data

    @staticmethod
    async def get_users(
        search: str | None = None,
        tag: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        async with async_session() as session:
            query = select(UserProfile).order_by(UserProfile.last_seen.desc().nullslast())

            if search:
                pattern = f"%{search}%"
                query = query.where(
                    or_(
                        UserProfile.first_name.ilike(pattern),
                        UserProfile.last_name.ilike(pattern),
                        UserProfile.username.ilike(pattern),
                        UserProfile.phone.ilike(pattern),
                        UserProfile.notes.ilike(pattern),
                    )
                )

            if tag:
                query = query.where(UserProfile.tags.ilike(f"%{tag}%"))

            count_query = select(func.count()).select_from(query.subquery())
            total = (await session.execute(count_query)).scalar() or 0

            result = await session.execute(
                query.offset((page - 1) * per_page).limit(per_page)
            )
            profiles = result.scalars().all()

            users = []
            for p in profiles:
                stats = await CrmService._quick_stats(session, p.telegram_user_id)
                users.append(CrmService._profile_to_dict(p, stats))

            return {"users": users, "total": total, "page": page, "per_page": per_page}

    @staticmethod
    async def _quick_stats(session, telegram_user_id: int) -> dict:
        result = await session.execute(
            select(
                func.count(Order.id).label("orders"),
                func.coalesce(func.sum(Order.total_amount), 0).label("spent"),
                func.max(Order.created_at).label("last_order"),
            )
            .where(
                Order.telegram_user_id == telegram_user_id,
                Order.status != "cancelled",
            )
        )
        row = result.one()
        return {
            "orders_count": row[0],
            "total_spent": row[1],
            "last_order": row[2].isoformat() if row[2] else None,
        }

    @staticmethod
    async def get_user_detail(telegram_user_id: int) -> dict | None:
        async with async_session() as session:
            profile = await session.get(UserProfile, telegram_user_id)
            if profile is None:
                return None

            stats = await CrmService._quick_stats(session, telegram_user_id)

            orders_result = await session.execute(
                select(Order)
                .where(Order.telegram_user_id == telegram_user_id)
                .order_by(Order.id.desc())
            )
            orders = [
                {
                    "id": o.id,
                    "status": o.status,
                    "total_amount": o.total_amount,
                    "promo_code": o.promo_code,
                    "discount_amount": o.discount_amount,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                    "items_count": 0,
                }
                for o in orders_result.scalars().all()
            ]

            items_result = await session.execute(
                select(OrderItem.product_name, func.sum(OrderItem.quantity).label("qty"))
                .join(Order, OrderItem.order_id == Order.id)
                .where(
                    Order.telegram_user_id == telegram_user_id,
                    Order.status != "cancelled",
                )
                .group_by(OrderItem.product_name)
                .order_by(func.sum(OrderItem.quantity).desc())
                .limit(5)
            )
            favorite_products = [
                {"name": row[0], "quantity": row[1]}
                for row in items_result.all()
            ]

            avg = stats["total_spent"] / stats["orders_count"] if stats["orders_count"] else 0

            return {
                **CrmService._profile_to_dict(profile, stats),
                "avg_order_value": round(avg),
                "orders": orders,
                "favorite_products": favorite_products,
            }

    @staticmethod
    async def get_communication_history(
        telegram_user_id: int,
        page: int = 1,
        per_page: int = 50,
    ) -> dict:
        async with async_session() as session:
            query = (
                select(CommunicationLog)
                .where(CommunicationLog.telegram_user_id == telegram_user_id)
                .order_by(CommunicationLog.id.desc())
            )

            count_query = select(func.count()).select_from(query.subquery())
            total = (await session.execute(count_query)).scalar() or 0

            result = await session.execute(
                query.offset((page - 1) * per_page).limit(per_page)
            )

            messages = [
                {
                    "id": m.id,
                    "direction": m.direction,
                    "message_type": m.message_type,
                    "text": m.text,
                    "admin_id": m.admin_id,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in result.scalars().all()
            ]

            return {"messages": messages, "total": total, "page": page, "per_page": per_page}

    @staticmethod
    async def update_notes(telegram_user_id: int, notes: str) -> bool:
        async with async_session() as session:
            profile = await session.get(UserProfile, telegram_user_id)
            if profile is None:
                return False
            profile.notes = notes.strip() or None
            await session.commit()
            return True

    @staticmethod
    async def add_tag(telegram_user_id: int, tag: str) -> bool:
        async with async_session() as session:
            profile = await session.get(UserProfile, telegram_user_id)
            if profile is None:
                return False
            tags = CrmService._parse_tags(profile.tags)
            tag = tag.strip()
            if tag and tag not in tags:
                tags.append(tag)
                profile.tags = ", ".join(tags)
                await session.commit()
            return True

    @staticmethod
    async def remove_tag(telegram_user_id: int, tag: str) -> bool:
        async with async_session() as session:
            profile = await session.get(UserProfile, telegram_user_id)
            if profile is None:
                return False
            tags = CrmService._parse_tags(profile.tags)
            tags = [t for t in tags if t != tag]
            profile.tags = ", ".join(tags) if tags else None
            await session.commit()
            return True

    @staticmethod
    async def get_all_tags() -> list[str]:
        async with async_session() as session:
            result = await session.execute(
                select(UserProfile.tags).where(UserProfile.tags.isnot(None))
            )
            all_tags = set()
            for row in result.all():
                all_tags.update(CrmService._parse_tags(row[0]))
            return sorted(all_tags)

    @staticmethod
    async def update_phone(telegram_user_id: int, phone: str | None) -> bool:
        async with async_session() as session:
            profile = await session.get(UserProfile, telegram_user_id)
            if profile is None:
                return False
            profile.phone = phone
            await session.commit()
            return True
