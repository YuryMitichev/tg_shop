from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.channel_import import ChannelPostButtonJob
from app.services.channel_import_service import ChannelImportService
from app.services.channel_post_button_service import ChannelPostButtonService
from app.services.channel_post_button_worker import ChannelPostButtonWorker
from app.services.catalog_admin_service import CatalogAdminService


class _FakeBot:
    def __init__(self, *, has_main_web_app: bool = True):
        self.has_main_web_app = has_main_web_app
        self.edits = []

    async def get_me(self):
        return SimpleNamespace(
            id=77,
            username="test_shop_bot",
            has_main_web_app=self.has_main_web_app,
        )

    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(status="administrator", can_edit_messages=True)

    async def edit_message_reply_markup(self, **kwargs):
        self.edits.append(kwargs)
        return True


class _FailingBot(_FakeBot):
    async def edit_message_reply_markup(self, **kwargs):
        raise RuntimeError("temporary Telegram outage")


async def _create_post(db_session) -> int:
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100777,
        channel_title="Buttons channel",
        channel_username="buttons_channel",
        connected_by=1,
    )
    await ChannelImportService.ingest_post(
        1,
        telegram_message_id=501,
        text="Два товара",
        media=[],
        raw_data={
            "source": "bot_api",
            "reply_markup_known": True,
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": "Доставка", "url": "https://example.com/delivery"}]
                ]
            },
        },
    )
    async with db_session() as session:
        from app.models.channel_import import ChannelPost

        return (
            await session.execute(select(ChannelPost.id).where(ChannelPost.telegram_message_id == 501))
        ).scalar_one()


@pytest.mark.asyncio
async def test_worker_preserves_source_buttons_and_adds_one_per_product(
    db_session, seed_data, monkeypatch
):
    monkeypatch.setattr(settings, "channel_product_buttons_enabled", True)
    monkeypatch.setattr(settings, "channel_product_buttons_pilot_shop_id", None)
    post_id = await _create_post(db_session)
    await ChannelPostButtonService.add_link(1, post_id, 1)
    await ChannelPostButtonService.add_link(1, post_id, 3)

    fake_bot = _FakeBot()
    monkeypatch.setattr("app.bot.bot.get_bot", lambda shop_id: fake_bot)
    worker = ChannelPostButtonWorker()
    job_id = await worker.claim_job("test-worker")
    assert job_id is not None
    await worker.process_job(job_id)

    assert len(fake_bot.edits) == 1
    markup = fake_bot.edits[0]["reply_markup"].model_dump(mode="json", exclude_none=True)
    rows = markup["inline_keyboard"]
    assert rows[0][0]["text"] == "Доставка"
    assert [row[0]["text"] for row in rows[1:]] == ["🛍 Кашемир", "🛍 Диффузор Кашемир"]
    assert rows[1][0]["url"].endswith("?startapp=shop_1_product_1")
    assert rows[2][0]["url"].endswith("?startapp=shop_1_product_3")

    async with db_session() as session:
        job = await session.get(ChannelPostButtonJob, job_id)
        assert job.status == "completed"


@pytest.mark.asyncio
async def test_duplicate_link_is_rejected(db_session, seed_data, monkeypatch):
    monkeypatch.setattr(settings, "channel_product_buttons_enabled", True)
    monkeypatch.setattr(settings, "channel_product_buttons_pilot_shop_id", None)
    post_id = await _create_post(db_session)
    await ChannelPostButtonService.add_link(1, post_id, 1)

    with pytest.raises(ValueError, match="уже прикреплён"):
        await ChannelPostButtonService.add_link(1, post_id, 1)


@pytest.mark.asyncio
async def test_missing_main_app_needs_action_without_removing_product(
    db_session, seed_data, monkeypatch
):
    monkeypatch.setattr(settings, "channel_product_buttons_enabled", True)
    monkeypatch.setattr(settings, "channel_product_buttons_pilot_shop_id", None)
    post_id = await _create_post(db_session)
    await ChannelPostButtonService.add_link(1, post_id, 1)

    fake_bot = _FakeBot(has_main_web_app=False)
    monkeypatch.setattr("app.bot.bot.get_bot", lambda shop_id: fake_bot)
    worker = ChannelPostButtonWorker()
    job_id = await worker.claim_job("test-worker")
    assert job_id is not None
    await worker.process_job(job_id)

    result = await ChannelPostButtonService.list_links(1, post_id)
    assert result["links"][0]["product_id"] == 1
    assert result["sync"]["status"] == "needs_action"
    assert result["sync"]["error_code"] == "main_app_missing"
    assert fake_bot.edits == []


@pytest.mark.asyncio
async def test_old_post_requires_explicit_markup_replacement(
    db_session, seed_data, monkeypatch
):
    monkeypatch.setattr(settings, "channel_product_buttons_enabled", True)
    monkeypatch.setattr(settings, "channel_product_buttons_pilot_shop_id", None)
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100778,
        channel_title="Legacy channel",
        channel_username=None,
        connected_by=1,
    )
    await ChannelImportService.ingest_post(
        1, telegram_message_id=502, text="Старый товар", media=[]
    )
    async with db_session() as session:
        from app.models.channel_import import ChannelPost

        post_id = (
            await session.execute(select(ChannelPost.id).where(ChannelPost.telegram_message_id == 502))
        ).scalar_one()

    with pytest.raises(ValueError, match="Неизвестно"):
        await ChannelPostButtonService.retry_post(1, post_id)
    result = await ChannelPostButtonService.retry_post(
        1, post_id, allow_replace_unknown=True
    )
    assert result["source_reply_markup_known"] is True


@pytest.mark.asyncio
async def test_disabling_product_removes_only_managed_button(
    db_session, seed_data, monkeypatch
):
    monkeypatch.setattr(settings, "channel_product_buttons_enabled", True)
    monkeypatch.setattr(settings, "channel_product_buttons_pilot_shop_id", None)
    post_id = await _create_post(db_session)
    await ChannelPostButtonService.add_link(1, post_id, 1)

    initial_worker = ChannelPostButtonWorker()
    first_job_id = await initial_worker.claim_job("initial-worker")
    assert first_job_id is not None
    fake_bot = _FakeBot()
    monkeypatch.setattr("app.bot.bot.get_bot", lambda shop_id: fake_bot)
    await initial_worker.process_job(first_job_id)

    assert await CatalogAdminService.toggle_active(1, 1) is False
    worker = ChannelPostButtonWorker()
    job_id = await worker.claim_job("lifecycle-worker")
    assert job_id is not None
    await worker.process_job(job_id)

    markup = fake_bot.edits[-1]["reply_markup"].model_dump(mode="json", exclude_none=True)
    assert markup["inline_keyboard"] == [
        [{"text": "Доставка", "url": "https://example.com/delivery"}]
    ]


@pytest.mark.asyncio
async def test_temporary_error_is_retried_without_duplicate_side_effect(
    db_session, seed_data, monkeypatch
):
    monkeypatch.setattr(settings, "channel_product_buttons_enabled", True)
    monkeypatch.setattr(settings, "channel_product_buttons_pilot_shop_id", None)
    monkeypatch.setattr("app.services.channel_post_button_worker.random.uniform", lambda *_: 0)
    post_id = await _create_post(db_session)
    await ChannelPostButtonService.add_link(1, post_id, 1)
    monkeypatch.setattr("app.bot.bot.get_bot", lambda shop_id: _FailingBot())

    worker = ChannelPostButtonWorker()
    job_id = await worker.claim_job("retry-worker")
    assert job_id is not None
    await worker.process_job(job_id)

    async with db_session() as session:
        job = await session.get(ChannelPostButtonJob, job_id)
        assert job.status == "retry_wait"
        assert job.attempts == 1
        assert job.error_code == "temporary_telegram_error"
