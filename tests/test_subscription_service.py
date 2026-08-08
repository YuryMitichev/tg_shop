from datetime import datetime, timedelta, timezone

import pytest

from app.services.subscription_service import SubscriptionService
from app.models.subscription import Subscription, SubscriptionPlan


@pytest.fixture
async def plans(db_session):
    """Создаёт тестовые тарифы."""
    async with db_session() as session:
        session.add_all([
            SubscriptionPlan(
                id=1,
                name="Триал 7 дней",
                price=0,
                duration_days=7,
                is_trial=True,
            ),
            SubscriptionPlan(
                id=2,
                name="Подписка — 1 месяц",
                description="Полный функционал магазина. Стоимость: 5000₽/мес.",
                price=5000,
                duration_days=30,
                is_trial=False,
            ),
            SubscriptionPlan(
                id=3,
                name="Подписка — 6 месяцев",
                description="Полный функционал магазина. Выгода 3000₽ (скидка 10%).",
                price=27000,
                duration_days=180,
                is_trial=False,
            ),
            SubscriptionPlan(
                id=4,
                name="Подписка — 12 месяцев",
                description="Полный функционал магазина. Выгода 12000₽ (скидка 20%).",
                price=48000,
                duration_days=365,
                is_trial=False,
            ),
        ])
        await session.commit()
    return {1: "Триал", 2: "1 мес", 3: "6 мес", 4: "12 мес"}


class TestGetPlans:

    async def test_get_plans_excludes_trial(self, db_session, seed_data, plans):
        result = await SubscriptionService.get_plans()

        ids = [p["id"] for p in result]
        assert 2 in ids
        assert 3 in ids
        assert 1 not in ids

    async def test_get_plans_sorted_by_price(self, db_session, seed_data, plans):
        result = await SubscriptionService.get_plans()

        assert result[0]["price"] <= result[1]["price"]
        assert result[0]["id"] == 2
        assert result[1]["id"] == 3

    async def test_get_plans_includes_features(self, db_session, seed_data, plans):
        async with db_session() as session:
            from app.models.subscription import SubscriptionPlan
            plan = await session.get(SubscriptionPlan, 2)
            plan.features = '["Каталог без лимита"]'
            await session.commit()

        result = await SubscriptionService.get_plans()
        plan_start = next(p for p in result if p["id"] == 2)
        assert isinstance(plan_start["features"], list)
        assert "Каталог без лимита" in plan_start["features"]

    async def test_get_plans_features_empty_when_null(self, db_session, seed_data, plans):
        result = await SubscriptionService.get_plans()
        for p in result:
            assert p["features"] == []


class TestGetPlan:

    async def test_get_plan_basic(self, db_session, seed_data, plans):
        plan = await SubscriptionService.get_plan(2)
        assert plan is not None
        assert plan["name"] == "Подписка — 1 месяц"
        assert plan["is_trial"] is False

    async def test_get_plan_not_found(self, db_session, seed_data, plans):
        plan = await SubscriptionService.get_plan(999)
        assert plan is None

    async def test_get_plan_includes_features(self, db_session, seed_data, plans):
        async with db_session() as session:
            from app.models.subscription import SubscriptionPlan
            plan = await session.get(SubscriptionPlan, 2)
            plan.features = '["Каталог без лимита", "CRM клиентов"]'
            await session.commit()

        result = await SubscriptionService.get_plan(2)
        assert result is not None
        assert isinstance(result["features"], list)
        assert "Каталог без лимита" in result["features"]


class TestStartTrial:

    async def test_start_trial_creates_subscription(self, db_session, seed_data, plans):
        result = await SubscriptionService.start_trial(shop_id=1)

        assert result is not None
        assert result["shop_id"] == 1
        assert result["status"] == "trial"

    async def test_start_trial_extends_existing(self, db_session, seed_data, plans):
        await SubscriptionService.start_trial(shop_id=1)
        result = await SubscriptionService.start_trial(shop_id=1)

        assert result is not None
        assert result["status"] == "trial"


class TestGetActiveSubscription:

    async def test_no_subscription(self, db_session, seed_data, plans):
        result = await SubscriptionService.get_active_subscription(shop_id=1)
        assert result is None

    async def test_active_trial(self, db_session, seed_data, plans):
        await SubscriptionService.start_trial(shop_id=1)
        result = await SubscriptionService.get_active_subscription(shop_id=1)

        assert result is not None
        assert result["is_active"] is True
        assert result["status"] == "trial"

    async def test_expired_trial(self, db_session, seed_data, plans):
        now = datetime.now(timezone.utc)

        async with db_session() as session:
            session.add(Subscription(
                shop_id=1,
                plan_id=1,
                status="trial",
                started_at=now - timedelta(days=10),
                expires_at=now - timedelta(days=3),
            ))
            await session.commit()

        result = await SubscriptionService.get_active_subscription(shop_id=1)
        assert result is not None
        assert result["is_active"] is False
        assert result["status"] == "expired"


class TestActivatePaidSubscription:

    async def test_activate_from_scratch(self, db_session, seed_data, plans):
        result = await SubscriptionService.activate_paid_subscription(
            shop_id=1, plan_id=2, payment_id="yk_test_123"
        )

        assert result is not None
        assert result["status"] == "active"
        assert result["plan_id"] == 2

    async def test_activate_extends_active(self, db_session, seed_data, plans):
        await SubscriptionService.start_trial(shop_id=1)
        sub_before = await SubscriptionService.get_active_subscription(shop_id=1)
        expires_before = sub_before["expires_at"]

        result = await SubscriptionService.activate_paid_subscription(
            shop_id=1, plan_id=2, payment_id="yk_test_456"
        )

        assert result is not None
        assert result["status"] == "active"
        assert result["expires_at"] > expires_before

    async def test_activate_after_expiry(self, db_session, seed_data, plans):
        now = datetime.now(timezone.utc)

        async with db_session() as session:
            session.add(Subscription(
                shop_id=1,
                plan_id=1,
                status="trial",
                started_at=now - timedelta(days=10),
                expires_at=now - timedelta(days=3),
            ))
            await session.commit()

        result = await SubscriptionService.activate_paid_subscription(
            shop_id=1, plan_id=2, payment_id="yk_test_789"
        )

        assert result is not None
        assert result["status"] == "active"

    async def test_activate_trial_plan_fails(self, db_session, seed_data, plans):
        result = await SubscriptionService.activate_paid_subscription(
            shop_id=1, plan_id=1, payment_id="yk_test"
        )
        assert result is None

    async def test_activate_nonexistent_plan_fails(self, db_session, seed_data, plans):
        result = await SubscriptionService.activate_paid_subscription(
            shop_id=1, plan_id=999, payment_id="yk_test"
        )
        assert result is None


class TestGetExpiredShops:

    async def test_expired_shop_returned(self, db_session, seed_data, plans):
        now = datetime.now(timezone.utc)

        async with db_session() as session:
            session.add(Subscription(
                shop_id=1,
                plan_id=1,
                status="trial",
                started_at=now - timedelta(days=10),
                expires_at=now - timedelta(days=3),
            ))
            await session.commit()

        expired = await SubscriptionService.get_expired_shops()
        assert 1 in expired

    async def test_active_shop_not_returned(self, db_session, seed_data, plans):
        await SubscriptionService.start_trial(shop_id=1)

        expired = await SubscriptionService.get_expired_shops()
        assert 1 not in expired


class TestGetExpiringShops:

    async def test_expiring_within_24h(self, db_session, seed_data, plans):
        now = datetime.now(timezone.utc)

        async with db_session() as session:
            session.add(Subscription(
                shop_id=1,
                plan_id=1,
                status="trial",
                started_at=now - timedelta(days=6),
                expires_at=now + timedelta(hours=12),
            ))
            await session.commit()

        expiring = await SubscriptionService.get_expiring_shops(hours=24)
        assert len(expiring) == 1
        assert expiring[0]["shop_id"] == 1

    async def test_not_expiring_soon(self, db_session, seed_data, plans):
        now = datetime.now(timezone.utc)

        async with db_session() as session:
            session.add(Subscription(
                shop_id=1,
                plan_id=1,
                status="trial",
                started_at=now,
                expires_at=now + timedelta(days=6),
            ))
            await session.commit()

        expiring = await SubscriptionService.get_expiring_shops(hours=24)
        assert len(expiring) == 0

    async def test_already_expired_not_included(self, db_session, seed_data, plans):
        now = datetime.now(timezone.utc)

        async with db_session() as session:
            session.add(Subscription(
                shop_id=1,
                plan_id=1,
                status="trial",
                started_at=now - timedelta(days=10),
                expires_at=now - timedelta(hours=2),
            ))
            await session.commit()

        expiring = await SubscriptionService.get_expiring_shops(hours=24)
        assert len(expiring) == 0


class TestMarkExpired:

    async def test_mark_expired(self, db_session, seed_data, plans):
        await SubscriptionService.start_trial(shop_id=1)

        await SubscriptionService.mark_expired(shop_id=1)

        async with db_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(Subscription).where(Subscription.shop_id == 1)
            )
            sub = result.scalar_one()
            assert sub.status == "expired"

    async def test_mark_expired_already_expired(self, db_session, seed_data, plans):
        await SubscriptionService.start_trial(shop_id=1)
        await SubscriptionService.mark_expired(shop_id=1)
        await SubscriptionService.mark_expired(shop_id=1)

    async def test_mark_expired_no_subscription(self, db_session, seed_data, plans):
        await SubscriptionService.mark_expired(shop_id=999)


class TestEnsureDefaultPlans:

    async def test_creates_all_three_plans(self, db_session):
        await SubscriptionService.ensure_default_plans()

        async with db_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(SubscriptionPlan))
            plans = {p.name: p for p in result.scalars().all()}

        assert "Триал 7 дней" in plans
        assert "Подписка — 1 месяц" in plans
        assert "Подписка — 6 месяцев" in plans
        assert "Подписка — 12 месяцев" in plans

        assert plans["Триал 7 дней"].price == 0
        assert plans["Триал 7 дней"].is_trial is True

        assert plans["Подписка — 1 месяц"].price == 5000
        assert plans["Подписка — 1 месяц"].is_trial is False

        assert plans["Подписка — 6 месяцев"].price == 27000
        assert plans["Подписка — 6 месяцев"].is_trial is False

        assert plans["Подписка — 12 месяцев"].price == 48000
        assert plans["Подписка — 12 месяцев"].is_trial is False

    async def test_idempotent(self, db_session):
        await SubscriptionService.ensure_default_plans()
        await SubscriptionService.ensure_default_plans()

        async with db_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(SubscriptionPlan))
            plans = result.scalars().all()

        assert len(plans) == 4

    async def test_features_stored_as_json(self, db_session):
        import json as _json

        await SubscriptionService.ensure_default_plans()

        async with db_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.name == "Подписка — 1 месяц")
            )
            plan = result.scalar_one()
            features = _json.loads(plan.features)

        assert isinstance(features, list)
        assert len(features) > 0
        assert any("Каталог" in f for f in features)
