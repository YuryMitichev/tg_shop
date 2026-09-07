from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import scripts.channel_e2e_smoke as smoke
from app.models.channel_import import (
    CatalogAnalysisRun,
    CatalogImportJob,
    ChannelConnection,
    ChannelPost,
)
from app.models.subscription import Subscription, SubscriptionPlan
from app.models.shop import Shop


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _prepare_smoke_shop(db_session, *, name: str = "Svoi Kanal Smoke Bot"):
    now = _utcnow()
    async with db_session() as session:
        shop = await session.get(Shop, 1)
        shop.name = name
        session.add(
            SubscriptionPlan(
                id=10,
                name="Пробный период — 14 дней",
                price=0,
                duration_days=14,
                is_trial=True,
                is_active=True,
            )
        )
        session.add(
            Subscription(
                shop_id=1,
                plan_id=10,
                status="expired",
                started_at=now - timedelta(days=8),
                expires_at=now - timedelta(days=1),
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_ensure_smoke_access_renews_only_dedicated_shop(
    db_session, seed_data, monkeypatch
):
    monkeypatch.setattr(smoke, "async_session", db_session)
    await _prepare_smoke_shop(db_session)

    await smoke._ensure_smoke_access(1)

    async with db_session() as session:
        subscription = (
            await session.execute(
                select(Subscription).where(Subscription.shop_id == 1)
            )
        ).scalar_one()
    assert subscription.status == "trial"
    assert subscription.plan_id == 10
    assert subscription.expires_at > _utcnow() + timedelta(days=1)


@pytest.mark.asyncio
async def test_ensure_smoke_access_rejects_regular_shop(
    db_session, seed_data, monkeypatch
):
    monkeypatch.setattr(smoke, "async_session", db_session)

    with pytest.raises(RuntimeError, match="dedicated shop name is invalid"):
        await smoke._ensure_smoke_access(1)


@pytest.mark.asyncio
async def test_wait_for_result_reports_subscription_block_immediately(
    db_session, seed_data, monkeypatch
):
    monkeypatch.setattr(smoke, "async_session", db_session)
    async with db_session() as session:
        connection = ChannelConnection(
            id=1,
            shop_id=1,
            channel_id=-100123,
            channel_title="Smoke",
            connected_by=1,
        )
        post = ChannelPost(
            id=1,
            shop_id=1,
            connection_id=1,
            telegram_message_id=99,
            text="SMOKE-test",
            status="subscription_blocked",
        )
        job = CatalogImportJob(
            id=1,
            shop_id=1,
            post_id=1,
            post_version=1,
            status="subscription_blocked",
        )
        session.add_all([connection, post, job])
        await session.commit()

    result = await smoke._wait_for_result(1, 99, timeout=1)

    assert result["job_status"] == "subscription_blocked"
    assert result["ai_run"] is False


@pytest.mark.asyncio
async def test_wait_for_result_uses_latest_cloud_ai_retry(
    db_session, seed_data, monkeypatch
):
    monkeypatch.setattr(smoke, "async_session", db_session)
    async with db_session() as session:
        connection = ChannelConnection(
            id=1,
            shop_id=1,
            channel_id=-100123,
            channel_title="Smoke",
            connected_by=1,
        )
        post = ChannelPost(
            id=1,
            shop_id=1,
            connection_id=1,
            telegram_message_id=100,
            text="SMOKE-retry",
            status="drafted",
        )
        job = CatalogImportJob(
            id=1,
            shop_id=1,
            post_id=1,
            post_version=1,
            status="completed",
        )
        session.add_all([connection, post, job])
        await session.flush()
        session.add_all(
            [
                CatalogAnalysisRun(
                    shop_id=1,
                    job_id=1,
                    run_type="cloud_ai",
                    error="first attempt failed",
                ),
                CatalogAnalysisRun(
                    shop_id=1,
                    job_id=1,
                    run_type="cloud_ai",
                    result={"classification": "product"},
                ),
            ]
        )
        await session.commit()

    result = await smoke._wait_for_result(1, 100, timeout=1)

    assert result["ai_run"] is True
    assert result["ai_error"] is False
