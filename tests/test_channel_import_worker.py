from sqlalchemy import select
import pytest

from app.core.config import settings
from app.models.channel_import import CatalogImportJob, ChannelPost
from app.services.channel_import_service import ChannelImportService
from app.services.channel_import_worker import ChannelImportWorker


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
