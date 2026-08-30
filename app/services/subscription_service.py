import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.cache import TTLCache
from app.core.pricing import (
    CANONICAL_SUBSCRIPTION_PLANS,
    TRIAL_DURATION_DAYS as DEFAULT_TRIAL_DURATION_DAYS,
    is_canonical_paid_plan,
)
from app.database.db import async_session
from app.models.subscription import Subscription, SubscriptionPlan


def _utcnow() -> datetime:
    """UTC без tzinfo — для совместимости с TIMESTAMP WITHOUT TIME ZONE."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SubscriptionService:
    """Управление подписками магазинов."""

    TRIAL_DURATION_DAYS = DEFAULT_TRIAL_DURATION_DAYS

    _active_cache: TTLCache = TTLCache(ttl=30)

    PLANS_SEED = CANONICAL_SUBSCRIPTION_PLANS

    @staticmethod
    async def ensure_default_plans() -> None:
        """Синхронизирует единственные действующие тарифы платформы."""
        async with async_session() as session:
            result = await session.execute(
                select(SubscriptionPlan).order_by(SubscriptionPlan.id)
            )
            existing_plans = list(result.scalars().all())
            canonical_plans: list[SubscriptionPlan] = []

            for plan_data in SubscriptionService.PLANS_SEED:
                matching = next(
                    (
                        plan
                        for plan in existing_plans
                        if plan.name == plan_data["name"]
                        and plan.is_trial == plan_data["is_trial"]
                        and plan not in canonical_plans
                    ),
                    None,
                )

                if matching is None and plan_data["is_trial"]:
                    matching = next(
                        (
                            plan
                            for plan in existing_plans
                            if plan.is_trial and plan not in canonical_plans
                        ),
                        None,
                    )

                if matching is None:
                    matching = SubscriptionPlan(
                        name=plan_data["name"],
                        description=plan_data["description"],
                        price=plan_data["price"],
                        duration_days=plan_data["duration_days"],
                        is_trial=plan_data["is_trial"],
                        is_active=True,
                        features=json.dumps(plan_data["features"], ensure_ascii=False),
                    )
                    session.add(matching)
                    existing_plans.append(matching)
                else:
                    matching.name = plan_data["name"]
                    matching.description = plan_data["description"]
                    matching.price = plan_data["price"]
                    matching.duration_days = plan_data["duration_days"]
                    matching.is_trial = plan_data["is_trial"]
                    matching.is_active = True
                    matching.features = json.dumps(
                        plan_data["features"], ensure_ascii=False
                    )

                canonical_plans.append(matching)

            for plan in existing_plans:
                if plan not in canonical_plans:
                    plan.is_active = False

            await session.commit()

    @staticmethod
    async def get_trial_plan() -> dict | None:
        async with async_session() as session:
            result = await session.execute(
                select(SubscriptionPlan)
                .where(
                    SubscriptionPlan.is_trial == True,  # noqa: E712
                    SubscriptionPlan.is_active == True,  # noqa: E712
                )
                .order_by(SubscriptionPlan.id)
                .limit(1)
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

        now = _utcnow()
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
            SubscriptionService._active_cache.invalidate(shop_id)
            return {
                "shop_id": shop_id,
                "status": "trial",
                "expires_at": expires.isoformat(),
            }

    @staticmethod
    async def get_active_subscription(shop_id: int) -> dict | None:
        """Возвращает активную подписку магазина или None."""
        now = _utcnow()

        async with async_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.shop_id == shop_id)
            )
            sub = result.scalar_one_or_none()

            if sub is None:
                return None

            is_expired = sub.expires_at < now

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
        hit, cached = SubscriptionService._active_cache.get(shop_id)
        if hit:
            return cached

        sub = await SubscriptionService.get_active_subscription(shop_id)
        result = sub is not None and sub["is_active"]
        SubscriptionService._active_cache.set(shop_id, result)
        return result

    @staticmethod
    async def get_expired_shops() -> list[int]:
        """Возвращает shop_id всех магазинов с истекшей подпиской."""
        now = _utcnow()

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
                    "features": json.loads(p.features) if p.features else [],
                }
                for p in result.scalars().all()
                if is_canonical_paid_plan(
                    name=p.name,
                    duration_days=p.duration_days,
                    price=p.price,
                )
            ]

    @staticmethod
    async def get_plan(plan_id: int) -> dict | None:
        async with async_session() as session:
            plan = await session.get(SubscriptionPlan, plan_id)
            if plan is None:
                return None
            return {
                "id": plan.id,
                "name": plan.name,
                "price": plan.price,
                "duration_days": plan.duration_days,
                "is_trial": plan.is_trial,
                "is_active": plan.is_active,
                "features": json.loads(plan.features) if plan.features else [],
            }

    @staticmethod
    async def activate_paid_subscription(
        shop_id: int, plan_id: int, payment_id: str
    ) -> dict | None:
        """
        Активирует или продлевает платную подписку.

        Если подписка ещё активна — продлевает от текущей даты истечения.
        Если истекла — от текущего момента.
        """
        plan = await SubscriptionService.get_plan(plan_id)
        if plan is None or plan["is_trial"]:
            return None

        now = _utcnow()
        duration = timedelta(days=plan["duration_days"])

        async with async_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.shop_id == shop_id)
            )
            sub = result.scalar_one_or_none()

            if sub is not None:
                if sub.external_payment_id == payment_id:
                    return {
                        "shop_id": shop_id,
                        "status": sub.status,
                        "expires_at": sub.expires_at.isoformat(),
                        "plan_id": sub.plan_id,
                    }

                base = max(now, sub.expires_at)
                new_expires = base + duration

                sub.plan_id = plan_id
                sub.status = "active"
                sub.expires_at = new_expires
                sub.cancelled_at = None
                sub.external_payment_id = payment_id
            else:
                new_expires = now + duration
                sub = Subscription(
                    shop_id=shop_id,
                    plan_id=plan_id,
                    status="active",
                    started_at=now,
                    expires_at=new_expires,
                    external_payment_id=payment_id,
                )
                session.add(sub)

            await session.commit()
            SubscriptionService._active_cache.invalidate(shop_id)
            return {
                "shop_id": shop_id,
                "status": "active",
                "expires_at": new_expires.isoformat(),
                "plan_id": plan_id,
            }

    @staticmethod
    async def get_expiring_shops(hours: int = 24) -> list[dict]:
        """Возвращает магазины, чей триал истекает в ближайшие N часов.

        Только те, у кого статус trial и подписка ещё не истекла.
        """
        now = _utcnow()
        threshold = now + timedelta(hours=hours)

        async with async_session() as session:
            result = await session.execute(
                select(Subscription, Subscription.shop_id).where(
                    Subscription.status == "trial",
                    Subscription.expires_at >= now,
                    Subscription.expires_at <= threshold,
                )
            )
            rows = result.all()
            return [
                {
                    "shop_id": row[1],
                    "expires_at": row[0].expires_at.isoformat(),
                }
                for row in rows
            ]

    @staticmethod
    async def mark_expired(shop_id: int) -> None:
        """Помечает подписку как истекшую."""
        async with async_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.shop_id == shop_id)
            )
            sub = result.scalar_one_or_none()
            if sub is not None and sub.status != "expired":
                sub.status = "expired"
                await session.commit()
                SubscriptionService._active_cache.invalidate(shop_id)
