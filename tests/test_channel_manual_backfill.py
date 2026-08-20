from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api.main import create_app
from app.core.config import settings
from app.models.channel_import import (
    CatalogImportJob,
    ChannelManualBackfillSession,
    ChannelPost,
    ChannelPostMedia,
)
from app.services.channel_import_service import ChannelImportService
from app.services.channel_manual_backfill_service import ChannelManualBackfillService
from app.services.channel_manual_backfill_worker import ChannelManualBackfillWorker


CHANNEL_ID = -1001234567890


@pytest.fixture(autouse=True)
def _enable_channel_import(monkeypatch):
    monkeypatch.setattr(settings, "channel_import_enabled", True)
    monkeypatch.setattr(settings, "channel_import_pilot_shop_id", None)


def _forwarded_message(
    source_message_id: int,
    *,
    channel_id: int = CHANNEL_ID,
    media_group_id: str | None = None,
    text: str | None = None,
    photo_id: str | None = None,
):
    photos = []
    if photo_id:
        photos.append(
            SimpleNamespace(
                file_id=photo_id,
                file_unique_id=f"unique-{photo_id}",
            )
        )
    return SimpleNamespace(
        forward_origin=SimpleNamespace(
            type="channel",
            chat=SimpleNamespace(id=channel_id),
            message_id=source_message_id,
            date=datetime.now(timezone.utc),
        ),
        photo=photos,
        caption=text,
        text=None,
        media_group_id=media_group_id,
        message_id=10_000 + source_message_id,
    )


@pytest.mark.asyncio
async def test_manual_backfill_groups_album_and_is_idempotent(db_session, seed_data):
    await ChannelImportService.connect_channel(
        1,
        channel_id=CHANNEL_ID,
        channel_title="History channel",
        channel_username="history_channel",
        connected_by=1,
    )
    session_id, token = await ChannelManualBackfillService.create_session(1, "phone")
    assert await ChannelManualBackfillService.session_for_token(1, 1, token) == session_id

    first = _forwarded_message(
        101,
        media_group_id="forwarded-album",
        text="Набор свечей, 1500 ₽",
        photo_id="photo-1",
    )
    second = _forwarded_message(
        102,
        media_group_id="forwarded-album",
        photo_id="photo-2",
    )
    result_one = await ChannelManualBackfillService.accept_forward(1, 1, first)
    result_two = await ChannelManualBackfillService.accept_forward(1, 1, second)
    duplicate = await ChannelManualBackfillService.accept_forward(1, 1, first)

    assert result_one["received_publications"] == 1
    assert result_two["received_messages"] == 2
    assert result_two["received_publications"] == 1
    assert duplicate["duplicate"] is True

    await ChannelManualBackfillService.queue_processing(1, 1, session_id)
    worker = ChannelManualBackfillWorker()
    imported, _, _ = await worker._process_session(session_id)
    assert imported == 1

    # Повтор после сбоя безопасен: существующие post/job/media не размножаются.
    imported_again, _, _ = await worker._process_session(session_id)
    assert imported_again == 1
    async with db_session() as session:
        post = (await session.execute(select(ChannelPost))).scalar_one()
        assert post.telegram_message_id == 101
        assert post.text == "Набор свечей, 1500 ₽"
        assert (
            await session.execute(select(func.count()).select_from(ChannelPostMedia))
        ).scalar_one() == 2
        assert (
            await session.execute(select(func.count()).select_from(CatalogImportJob))
        ).scalar_one() == 1
        backfill = await session.get(ChannelManualBackfillSession, session_id)
        assert backfill.status == "completed"
        assert backfill.imported_publications == 1


@pytest.mark.asyncio
async def test_manual_backfill_rejects_non_owner_and_other_channel(db_session, seed_data):
    await ChannelImportService.connect_channel(
        1,
        channel_id=CHANNEL_ID,
        channel_title="Protected source",
        channel_username=None,
        connected_by=1,
    )
    session_id, _ = await ChannelManualBackfillService.create_session(1, "browser")

    assert (
        await ChannelManualBackfillService.accept_forward(
            1, 999, _forwarded_message(201, text="Чужое сообщение")
        )
        is None
    )
    rejected = await ChannelManualBackfillService.accept_forward(
        1,
        1,
        _forwarded_message(202, channel_id=-100999999, text="Другой канал"),
    )
    assert rejected == {"accepted": False, "reason": "wrong_channel"}
    async with db_session() as session:
        backfill = await session.get(ChannelManualBackfillSession, session_id)
        assert backfill.received_messages == 0
        assert backfill.rejected_messages == 1


@pytest.mark.asyncio
async def test_manual_backfill_worker_reclaims_only_expired_processing_lock(
    db_session, seed_data
):
    await ChannelImportService.connect_channel(
        1,
        channel_id=CHANNEL_ID,
        channel_title="Restart source",
        channel_username=None,
        connected_by=1,
    )
    session_id, _ = await ChannelManualBackfillService.create_session(1, "phone")
    await ChannelManualBackfillService.accept_forward(
        1, 1, _forwarded_message(301, text="Товар 900 ₽")
    )
    await ChannelManualBackfillService.queue_processing(1, 1, session_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with db_session() as session:
        backfill = await session.get(ChannelManualBackfillSession, session_id)
        backfill.status = "processing"
        backfill.available_at = now - timedelta(seconds=10)
        backfill.locked_by = "dead-worker"
        backfill.locked_until = now + timedelta(minutes=1)
        await session.commit()

    worker = ChannelManualBackfillWorker()
    assert await worker.claim_session("replacement") is None
    async with db_session() as session:
        backfill = await session.get(ChannelManualBackfillSession, session_id)
        backfill.locked_until = now - timedelta(seconds=1)
        await session.commit()
    assert await worker.claim_session("replacement") == session_id


@pytest.mark.asyncio
async def test_manual_backfill_failure_retries_are_bounded(db_session, seed_data):
    await ChannelImportService.connect_channel(
        1,
        channel_id=CHANNEL_ID,
        channel_title="Failure source",
        channel_username=None,
        connected_by=1,
    )
    session_id, _ = await ChannelManualBackfillService.create_session(1, "phone")
    await ChannelManualBackfillService.accept_forward(
        1, 1, _forwarded_message(401, text="Товар 1200 ₽")
    )
    await ChannelManualBackfillService.queue_processing(1, 1, session_id)

    with pytest.raises(ValueError, match="обрабатываются"):
        await ChannelManualBackfillService.create_session(1, "browser")

    worker = ChannelManualBackfillWorker()
    statuses = []
    for _ in range(4):
        await worker._fail_or_retry(session_id, RuntimeError("temporary failure"))
        async with db_session() as session:
            statuses.append(
                (await session.get(ChannelManualBackfillSession, session_id)).status
            )
    assert statuses == ["queued", "queued", "queued", "failed"]



class _FakeBot:
    async def get_me(self):
        return SimpleNamespace(username="history_shop_bot")

    async def send_message(self, *args, **kwargs):
        return SimpleNamespace(message_id=777)


@pytest.mark.asyncio
async def test_admin_chooses_browser_and_receives_manual_backfill_links(
    db_session,
    seed_data,
    active_subscription,
    admin_cookie,
    mock_admin_auth,
    monkeypatch,
):
    await ChannelImportService.connect_channel(
        1,
        channel_id=CHANNEL_ID,
        channel_title="API history source",
        channel_username="api_history",
        connected_by=1,
    )
    monkeypatch.setattr("app.api.routes.channel_import.get_bot", lambda _: _FakeBot())

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/admin/channel-import/manual-backfill",
            json={"device": "browser"},
            cookies=admin_cookie,
        )
        current = await client.get(
            "/api/admin/channel-import/manual-backfill",
            cookies=admin_cookie,
        )
        await ChannelManualBackfillService.accept_forward(
            1, 1, _forwarded_message(501, text="Выбранный товар 2500 ₽")
        )
        finish = await client.post(
            f"/api/admin/channel-import/manual-backfill/{response.json()['id']}/finish",
            cookies=admin_cookie,
        )

    assert response.status_code == 200
    assert response.json()["instruction_sent"] is True
    assert response.json()["telegram_web_url"].endswith("#@history_shop_bot")
    assert "?start=history_" in response.json()["telegram_deep_link"]
    assert current.status_code == 200
    assert current.json()["status"] == "collecting"
    assert finish.status_code == 200
    assert finish.json()["status"] == "queued"
