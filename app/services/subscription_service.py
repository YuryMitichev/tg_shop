from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database.db import async_session
from app.models.subscription import Subscription, SubscriptionPlan


class SubscriptionService:
    """Управление подписками магазинов."""

    TRIAL_DURATION_DAYS = 7
    DEFAULT_PLAN_NAME = "Базовый"

    @staticmethod
    async def ensure_default_plans() -> None:
        """Создаёт тариф по умолчанию и триал, если их ещё нет."""
        async with async_session() as session:
            trial = await session.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.is_trial == True)  # noqa: E712
            )
            if trial.scalar_one_or_none() is None:
                session.add(SubscriptionPlan(
                    name="Триал 7 дней",
                    description="Бесплатный пробный период",
                    price=0,
                    duration_days=7,
                    is_trial=True,
                ))

            basic = await session.execute(
                select(SubscriptionPlan).where(
                    SubscriptionPlan.name == SubscriptionService.DEFAULT_PLAN_NAME,
                    SubscriptionPlan.is_trial == False,  # noqa: E712
                )
            )
            if basic.scalar_one_or_none() is None:
                session.add(SubscriptionPlan(
                    name=SubscriptionService.DEFAULT_PLAN_NAME,
                    description="Базовый тариф",
                    price=990,
                    duration_days=30,
                    is_trial=False,
                ))

            await session.commit()

    @staticmethod
    async def get_trial_plan() -> dict | None:
        async with async_session() as session:
            result = await session.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.is_trial == True)  # noqa: E712
            )
            plan = result.scalar_one_or_none()
            if plan is None:
                return None
            return {"id": plan.id, "duration_days": plan.duration_days}

    @staticmethod
    async def start_trial(shop_id: int) -> dict | None:
        """Запускает триальный период для магазина."""
        plan = await SubscriptionService.get_trial_plan()
        if plan is None:
            return None

        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=plan["duration_days"])

        async with async_session() as session:
            existing = await session.execute(
                select(Subscription).where(Subscription.shop_id == shop_id)
            )
            sub = existing.scalar_one_or_none()

            if sub is not None:
                sub.plan_id = plan["id"]
                sub.status = "trial"
                sub.started_at = now
                sub.expires_at = expires
                sub.cancelled_at = None
            else:
                sub = Subscription(
                    shop_id=shop_id,
                    plan_id=plan["id"],
                    status="trial",
                    started_at=now,
                    expires_at=expires,
                )
                session.add(sub)

            await session.commit()
            return {
                "shop_id": shop_id,
                "status": "trial",
                "expires_at": expires.isoformat(),
            }

    @staticmethod
    async def get_active_subscription(shop_id: int) -> dict | None:
        """Возвращает активную подписку магазина или None."""
        now = datetime.now(timezone.utc)

        async with async_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.shop_id == shop_id)
            )
            sub = result.scalar_one_or_none()

            if sub is None:
                return None

            if sub.expires_at.tzinfo is None:
                sub_expires = sub.expires_at.replace(tzinfo=timezone.utc)
            else:
                sub_expires = sub.expires_at

            is_expired = sub_expires < now

            return {
                "id": sub.id,
                "shop_id": sub.shop_id,
                "plan_id": sub.plan_id,
                "status": "expired" if is_expired else sub.status,
                "started_at": sub.started_at.isoformat() if sub.started_at else None,
                "expires_at": sub.expires_at.isoformat(),
                "is_active": not is_expired,
            }

    @staticmethod
    async def is_shop_active(shop_id: int) -> bool:
        """True если у магазина активная (не истекшая) подписка."""
        sub = await SubscriptionService.get_active_subscription(shop_id)
        return sub is not None and sub["is_active"]

    @staticmethod
    async def get_expired_shops() -> list[int]:
        """Возвращает shop_id всех магазинов с истекшей подпиской."""
        now = datetime.now(timezone.utc)

        async with async_session() as session:
            result = await session.execute(
                select(Subscription).where(
                    Subscription.status.in_(["trial", "active"]),
                    Subscription.expires_at < now,
                )
            )
            return [sub.shop_id for sub in result.scalars().all()]

    @staticmethod
    async def get_plans() -> list[dict]:
        """Возвращает все активные тарифы (кроме триала)."""
        async with async_session() as session:
            result = await session.execute(
                select(SubscriptionPlan).where(
                    SubscriptionPlan.is_active == True,  # noqa: E712
                    SubscriptionPlan.is_trial == False,  # noqa: E712
                ).order_by(SubscriptionPlan.price)
            )
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "price": p.price,
                    "duration_days": p.duration_days,
                }
                for p in result.scalars().all()
            ]
