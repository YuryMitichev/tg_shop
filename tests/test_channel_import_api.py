import pytest
from unittest.mock import AsyncMock
from sqlalchemy import select
from httpx import ASGITransport, AsyncClient

from app.api.main import create_app
from app.models.channel_import import CatalogImportCandidate
from app.models.channel_import import ChannelPost
from app.core.config import settings
from app.services.channel_import_service import ChannelImportService
from app.services.channel_storefront_service import ChannelStorefrontService


@pytest.mark.asyncio
async def test_admin_can_approve_complete_candidate(
    db_session,
    seed_data,
    active_subscription,
    admin_cookie,
    mock_admin_auth,
):
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100444,
        channel_title="API channel",
        channel_username=None,
        connected_by=1,
    )
    job_id = await ChannelImportService.ingest_post(
        1, telegram_message_id=5, text="Новый товар 800 ₽", media=[]
    )
    async with db_session() as session:
        candidate = CatalogImportCandidate(
            shop_id=1,
            job_id=job_id,
            position=0,
            status="pending",
            name="API товар",
            description="Описание",
            category_name="Свечи",
            currency="RUB",
            variants=[{"title": "100 г", "price": 800, "stock": 2, "currency": "RUB"}],
            attributes={},
            field_confidence={},
        )
        session.add(candidate)
        await session.commit()
        await session.refresh(candidate)
        candidate_id = candidate.id

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/admin/channel-import/candidates/{candidate_id}/approve",
            cookies=admin_cookie,
        )

    assert response.status_code == 200
    assert response.json()["product_id"] > 0


@pytest.mark.asyncio
async def test_admin_can_sync_pinned_storefront(
    db_session,
    seed_data,
    active_subscription,
    admin_cookie,
    mock_admin_auth,
    monkeypatch,
):
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100443,
        channel_title="Pinned storefront channel",
        channel_username=None,
        connected_by=1,
    )
    sync = AsyncMock(
        return_value={
            "message_id": 901,
            "status": "active",
            "error_code": None,
            "error": None,
            "updated_at": "2026-08-20T00:00:00",
        }
    )
    monkeypatch.setattr(ChannelStorefrontService, "sync", sync)

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/admin/channel-import/storefront-pin/sync",
            cookies=admin_cookie,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    sync.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_admin_can_save_stock_then_approve_candidate(
    db_session,
    seed_data,
    active_subscription,
    admin_cookie,
    mock_admin_auth,
):
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100445,
        channel_title="Stock channel",
        channel_username=None,
        connected_by=1,
    )
    job_id = await ChannelImportService.ingest_post(
        1, telegram_message_id=6, text="Товар 900 ₽", media=[]
    )
    async with db_session() as session:
        candidate = CatalogImportCandidate(
            shop_id=1,
            job_id=job_id,
            position=0,
            status="needs_manual",
            name="Товар с остатком",
            description="Описание",
            category_name="Свечи",
            currency="RUB",
            variants=[
                {"title": "150 г", "price": 900, "stock": None, "currency": "RUB"}
            ],
            attributes={},
            field_confidence={},
        )
        session.add(candidate)
        await session.commit()
        await session.refresh(candidate)
        candidate_id = candidate.id

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        patch_response = await client.patch(
            f"/api/admin/channel-import/candidates/{candidate_id}",
            json={
                "variants": [
                    {"title": "150 г", "price": 900, "stock": 7, "currency": "RUB"}
                ]
            },
            cookies=admin_cookie,
        )
        approve_response = await client.post(
            f"/api/admin/channel-import/candidates/{candidate_id}/approve",
            cookies=admin_cookie,
        )

    assert patch_response.status_code == 200
    assert patch_response.json()["variants"][0]["stock"] == 7
    assert approve_response.status_code == 200


def test_telegram_stock_helpers_handle_multiple_variants():
    from app.bot.handlers.channel_import import _next_missing_stock, _stock_prompt

    variants = [
        {"title": "100 г", "stock": 3},
        {"title": "200 г", "stock": None},
    ]

    assert _next_missing_stock(variants) == 1
    assert "200 г" in _stock_prompt(variants[1], 1, 2)


@pytest.mark.asyncio
async def test_admin_manages_post_product_links(
    db_session,
    seed_data,
    active_subscription,
    admin_cookie,
    mock_admin_auth,
    monkeypatch,
):
    monkeypatch.setattr(settings, "channel_product_buttons_enabled", True)
    monkeypatch.setattr(settings, "channel_product_buttons_pilot_shop_id", None)
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100446,
        channel_title="Links API channel",
        channel_username=None,
        connected_by=1,
    )
    await ChannelImportService.ingest_post(
        1,
        telegram_message_id=7,
        text="Товар со ссылкой",
        media=[],
        raw_data={"reply_markup_known": True, "reply_markup": None},
    )
    async with db_session() as session:
        post_id = (
            await session.execute(
                select(ChannelPost.id).where(ChannelPost.telegram_message_id == 7)
            )
        ).scalar_one()

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        add_response = await client.post(
            f"/api/admin/channel-import/posts/{post_id}/product-links",
            json={"product_id": 1},
            cookies=admin_cookie,
        )
        assert add_response.status_code == 200
        link_id = add_response.json()["links"][0]["id"]

        replace_response = await client.patch(
            f"/api/admin/channel-import/posts/{post_id}/product-links/{link_id}",
            json={"product_id": 3},
            cookies=admin_cookie,
        )
        assert replace_response.status_code == 200
        assert replace_response.json()["links"][0]["product_id"] == 3

        inactive_response = await client.post(
            f"/api/admin/channel-import/posts/{post_id}/product-links",
            json={"product_id": 2},
            cookies=admin_cookie,
        )
        assert inactive_response.status_code == 400

        delete_response = await client.delete(
            f"/api/admin/channel-import/posts/{post_id}/product-links/{link_id}",
            cookies=admin_cookie,
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["links"] == []
