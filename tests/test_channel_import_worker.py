from datetime import datetime, timedelta, timezone

from sqlalchemy import select
import pytest

from app.core.config import settings
from app.models.channel_import import (
    CatalogAnalysisRun,
    CatalogImportJob,
    ChannelConnection,
    ChannelPost,
)
from app.models.shop import Shop
from app.services.channel_import_service import ChannelImportService
from app.services.channel_import_worker import ChannelImportWorker
from app.utils.crypto import encrypt, token_hash


class _NeverAI:
    async def analyze_post(self, *args, **kwargs):
        raise AssertionError("AI не должен вызываться при исчерпанном бюджете")


@pytest.mark.asyncio
async def test_expired_subscription_blocks_processing(db_session, seed_data):
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100778,
        channel_title="Expired channel",
        channel_username=None,
        connected_by=1,
    )
    job_id = await ChannelImportService.ingest_post(
        1, telegram_message_id=9, text="Свеча 990 ₽", media=[]
    )
    await ChannelImportWorker(ai_service=_NeverAI())._process_job(job_id)
    async with db_session() as session:
        job = await session.get(CatalogImportJob, job_id)
        assert job.status == "subscription_blocked"


@pytest.mark.asyncio
async def test_budget_blocks_before_cloud_ai(
    db_session, seed_data, active_subscription, monkeypatch
):
    monkeypatch.setattr(settings, "channel_import_budget_usd", 0.0)
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100777,
        channel_title="Budget channel",
        channel_username=None,
        connected_by=1,
    )
    job_id = await ChannelImportService.ingest_post(
        1,
        telegram_message_id=1,
        text="Свеча 200 г, цена 990 ₽, в наличии",
        media=[],
    )
    await ChannelImportWorker(ai_service=_NeverAI())._process_job(job_id)
    async with db_session() as session:
        job = await session.get(CatalogImportJob, job_id)
        post = await session.get(ChannelPost, job.post_id)
        assert job.status == "budget_blocked"
        assert post.status == "budget_blocked"


@pytest.mark.asyncio
async def test_failed_job_gets_all_three_retry_delays(db_session, seed_data, monkeypatch):
    monkeypatch.setattr("app.services.channel_import_worker.random.uniform", lambda *_: 0)
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100776,
        channel_title="Retry channel",
        channel_username=None,
        connected_by=1,
    )
    job_id = await ChannelImportService.ingest_post(
        1, telegram_message_id=2, text="Товар 990 ₽", media=[]
    )
    worker = ChannelImportWorker(ai_service=_NeverAI())
    statuses = []
    for _ in range(4):
        await worker._fail_or_retry(job_id, RuntimeError("timeout"))
        async with db_session() as session:
            statuses.append((await session.get(CatalogImportJob, job_id)).status)
    assert statuses == ["queued", "queued", "queued", "failed"]


@pytest.mark.asyncio
async def test_claim_reclaims_only_expired_analyzing_job(db_session, seed_data):
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100775,
        channel_title="Restart recovery channel",
        channel_username=None,
        connected_by=1,
    )
    job_id = await ChannelImportService.ingest_post(
        1, telegram_message_id=3, text="Товар 1200 ₽", media=[]
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with db_session() as session:
        job = await session.get(CatalogImportJob, job_id)
        job.status = "analyzing"
        job.locked_by = "dead-worker"
        job.locked_until = now + timedelta(minutes=1)
        await session.commit()

    worker = ChannelImportWorker(ai_service=_NeverAI())
    assert await worker.claim_job("replacement-worker") is None

    async with db_session() as session:
        job = await session.get(CatalogImportJob, job_id)
        job.locked_until = now - timedelta(seconds=1)
        await session.commit()

    assert await worker.claim_job("replacement-worker") == job_id
    async with db_session() as session:
        job = await session.get(CatalogImportJob, job_id)
        assert job.status == "analyzing"
        assert job.locked_by == "replacement-worker"
        assert job.locked_until > now


@pytest.mark.asyncio
async def test_ai_budget_and_stats_are_isolated_per_shop(db_session, seed_data):
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100774,
        channel_title="First budget channel",
        channel_username=None,
        connected_by=1,
    )
    first_job_id = await ChannelImportService.ingest_post(
        1, telegram_message_id=4, text="Товар 1400 ₽", media=[]
    )

    async with db_session() as session:
        session.add(
            Shop(
                id=2,
                name="Second Shop",
                bot_token=encrypt("second:test-token"),
                bot_token_hash=token_hash("second:test-token"),
                owner_telegram_id=2,
            )
        )
        await session.flush()
        connection = ChannelConnection(
            shop_id=2,
            channel_id=-100773,
            channel_title="Second budget channel",
            connected_by=2,
        )
        session.add(connection)
        await session.flush()
        post = ChannelPost(
            shop_id=2,
            connection_id=connection.id,
            telegram_message_id=5,
        )
        session.add(post)
        await session.flush()
        second_job = CatalogImportJob(
            shop_id=2,
            post_id=post.id,
            post_version=1,
        )
        session.add(second_job)
        await session.flush()
        session.add_all(
            [
                CatalogAnalysisRun(
                    shop_id=1,
                    job_id=first_job_id,
                    run_type="cloud_ai",
                    input_tokens=100,
                    output_tokens=20,
                    cost_microusd=100_000,
                ),
                CatalogAnalysisRun(
                    shop_id=2,
                    job_id=second_job.id,
                    run_type="cloud_ai",
                    input_tokens=300,
                    output_tokens=60,
                    cost_microusd=300_000,
                ),
            ]
        )
        await session.commit()

    worker = ChannelImportWorker(ai_service=_NeverAI())
    async with db_session() as session:
        assert await worker._monthly_cost(session, 1) == 100_000
        assert await worker._monthly_cost(session, 2) == 300_000

    stats = await ChannelImportService.stats(1)
    assert stats["ai"]["input_tokens"] == 100
    assert stats["ai"]["output_tokens"] == 20
    assert stats["ai"]["cost_usd"] == 0.1
