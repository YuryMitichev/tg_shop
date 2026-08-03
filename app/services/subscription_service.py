import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database.db import async_session
from app.models.subscription import Subscription, SubscriptionPlan


class SubscriptionService:
    """Управление подписками магазинов."""

    TRIAL_DURATION_DAYS = 7

    PLANS_SEED = [
        {
            "name": "Триал 7 дней",
            "description": "Бесплатный пробный период — все возможности",
            "price": 0,
            "duration_days": 7,
            "is_trial": True,
            "features": [],
        },
        {
            "name": "Старт",
            "description": "Для микро-бизнеса и начинающих продавцов",
            "price": 690,
            "duration_days": 30,
            "is_trial": False,
            "features": [
                "Каталог товаров без лимита",
                "Заказы и корзина без лимита",
                "Админ-панель и мини-приложение",
                "CRM: профили клиентов",
                "Приём оплаты (СБП / карты)",
                "Промокоды",
                "Рассылки: 1 в неделю",
                "До 3 администраторов",
            ],
        },
        {
            "name": "Бизнес",
            "description": "Для растущих магазинов с потоком заказов",
            "price": 1490,
            "duration_days": 30,
            "is_trial": False,
            "features": [
                "Всё из тарифа «Старт»",
                "Рассылки без лимита",
                "Авто-теги клиентов",
                "Персональные офферы",
                "Расширенная аналитика продаж",
                "Администраторы без лимита",
                "Приоритетная поддержка",
            ],
        },
    ]

    @staticmethod
    async def ensure_default_plans() -> None:
        """Создаёт тарифы по умолчанию, если их ещё нет."""
        async with async_session() as session:
            for plan_data in SubscriptionService.PLANS_SEED:
                result = await session.execute(
                    select(SubscriptionPlan).where(
                        SubscriptionPlan.name == plan_data["name"],
                        SubscriptionPlan.is_trial == plan_data["is_trial"],
                    )
                )
                if result.scalar_one_or_none() is None:
                    session.add(SubscriptionPlan(
                        name=plan_data["name"],
                        description=plan_data["description"],
                        price=plan_data["price"],
                        duration_days=plan_data["duration_days"],
                        is_trial=plan_data["is_trial"],
                        features=json.dumps(plan_data["features"], ensure_ascii=False),
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
                    "features": json.loads(p.features) if p.features else [],
                }
                for p in result.scalars().all()
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

        now = datetime.now(timezone.utc)
        duration = timedelta(days=plan["duration_days"])

        async with async_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.shop_id == shop_id)
            )
            sub = result.scalar_one_or_none()

            if sub is not None:
                current_expires = sub.expires_at
                if current_expires.tzinfo is None:
                    current_expires = current_expires.replace(tzinfo=timezone.utc)

                base = max(now, current_expires)
                new_expires = base + duration

                sub.plan_id = plan_id
                sub.status = "active"
                sub.expires_at = new_expires.replace(tzinfo=None)
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
        now = datetime.now(timezone.utc)
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
