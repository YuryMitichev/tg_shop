import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import create_app
from app.models.channel_import import CatalogImportCandidate
from app.services.channel_import_service import ChannelImportService


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
