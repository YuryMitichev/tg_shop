from sqlalchemy import func, select
import pytest

from app.models.channel_import import (
    CatalogImportCandidate,
    CatalogImportJob,
    ChannelPost,
    ProductSourceRef,
)
from app.models.product import Product
from app.models.product_attribute_def import ProductAttributeDef
from app.services.channel_import_service import ChannelImportService
from app.core.config import settings


@pytest.mark.asyncio
async def test_realtime_only_connection_without_mtproto(
    db_session, seed_data, monkeypatch
):
    monkeypatch.setattr(settings, "telegram_api_id", None)
    monkeypatch.setattr(settings, "telegram_api_hash", None)
    monkeypatch.setattr(settings, "telegram_session", None)

    connection = await ChannelImportService.connect_channel(
        1,
        channel_id=-1001234500000,
        channel_title="Realtime only",
        channel_username="realtime_only",
        connected_by=1,
    )

    assert connection.backfill_status == "not_configured"
    with pytest.raises(ValueError, match="realtime"):
        await ChannelImportService.enqueue_backfill(1)


@pytest.mark.asyncio
async def test_approve_candidate_is_transactional_and_idempotent(db_session, seed_data):
    connection = await ChannelImportService.connect_channel(
        1,
        channel_id=-1001234567890,
        channel_title="Test channel",
        channel_username="test_channel",
        connected_by=1,
    )
    job_id = await ChannelImportService.ingest_post(
        1,
        telegram_message_id=101,
        text="Свеча Лён 200 г, цена 1200 ₽, в наличии 4 шт.",
        media=[{"file_id": "telegram-photo-id", "file_unique_id": "photo-1"}],
    )
    assert job_id is not None

    async with db_session() as session:
        candidate = CatalogImportCandidate(
            shop_id=1,
            job_id=job_id,
            position=0,
            status="pending",
            name="Свеча Лён",
            description="Свеча с ароматом льна",
            category_name="Новая коллекция",
            proposed_category=True,
            sku="LINEN-200",
            currency="RUB",
            variants=[
                {
                    "title": "200 г",
                    "price": 1200,
                    "stock": 4,
                    "currency": "RUB",
                    "attributes": {"Время горения": "45 часов"},
                }
            ],
            attributes={"Аромат": "Лён"},
            field_confidence={},
        )
        session.add(candidate)
        await session.commit()
        await session.refresh(candidate)
        candidate_id = candidate.id

    product_id = await ChannelImportService.approve_candidate(1, candidate_id)
    second_product_id = await ChannelImportService.approve_candidate(1, candidate_id)
    assert product_id == second_product_id

    async with db_session() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        assert product.name == "Свеча Лён"
        refs = (
            await session.execute(
                select(ProductSourceRef).where(ProductSourceRef.product_id == product_id)
            )
        ).scalars().all()
        assert len(refs) == 1
        product_count = (
            await session.execute(
                select(func.count()).select_from(Product).where(Product.name == "Свеча Лён")
            )
        ).scalar_one()
        assert product_count == 1
        labels = set(
            (
                await session.execute(
                    select(ProductAttributeDef.label).where(ProductAttributeDef.shop_id == 1)
                )
            ).scalars().all()
        )
        assert {"Аромат", "Время горения"} <= labels


@pytest.mark.asyncio
async def test_edit_supersedes_unpublished_draft(db_session, seed_data):
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100999,
        channel_title="Edit channel",
        channel_username=None,
        connected_by=1,
    )
    first_job_id = await ChannelImportService.ingest_post(
        1, telegram_message_id=42, text="Товар 500 ₽", media=[]
    )
    async with db_session() as session:
        session.add(
            CatalogImportCandidate(
                shop_id=1,
                job_id=first_job_id,
                position=0,
                status="pending",
                variants=[],
                attributes={},
                field_confidence={},
            )
        )
        await session.commit()

    second_job_id = await ChannelImportService.ingest_post(
        1, telegram_message_id=42, text="Товар 600 ₽", media=[], edited_at=None
    )
    assert second_job_id != first_job_id

    async with db_session() as session:
        old_candidate = (
            await session.execute(
                select(CatalogImportCandidate).where(
                    CatalogImportCandidate.job_id == first_job_id
                )
            )
        ).scalar_one()
        post = (await session.execute(select(ChannelPost))).scalar_one()
        assert old_candidate.status == "superseded"
        assert post.version == 2


@pytest.mark.asyncio
async def test_repeated_delivery_is_idempotent(db_session, seed_data):
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100998,
        channel_title="Idempotent channel",
        channel_username=None,
        connected_by=1,
    )
    first = await ChannelImportService.ingest_post(
        1, telegram_message_id=55, text="Свеча 700 ₽", media=[]
    )
    second = await ChannelImportService.ingest_post(
        1, telegram_message_id=55, text="Свеча 700 ₽", media=[]
    )
    assert first == second
    async with db_session() as session:
        count = (
            await session.execute(select(func.count()).select_from(CatalogImportJob))
        ).scalar_one()
        post = (await session.execute(select(ChannelPost))).scalar_one()
        assert count == 1
        assert post.version == 1


@pytest.mark.asyncio
async def test_duplicate_search_finds_similar_existing_product(db_session, seed_data):
    matches = await ChannelImportService.find_duplicates(
        1,
        {
            "name": "Диффузор Кашемир",
            "category_name": "Диффузоры",
            "variants": [{"price": 1290}],
        },
    )
    assert matches[0]["product_id"] == 3
    assert matches[0]["score"] >= 0.92


@pytest.mark.asyncio
async def test_approval_requires_stock(db_session, seed_data):
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100111,
        channel_title="No stock",
        channel_username=None,
        connected_by=1,
    )
    job_id = await ChannelImportService.ingest_post(
        1, telegram_message_id=7, text="Товар 100 ₽", media=[]
    )
    async with db_session() as session:
        candidate = CatalogImportCandidate(
            shop_id=1,
            job_id=job_id,
            position=0,
            status="needs_manual",
            name="Товар",
            description="",
            category_name="Свечи",
            currency="RUB",
            variants=[{"title": "—", "price": 100, "stock": None}],
            attributes={},
            field_confidence={},
        )
        session.add(candidate)
        await session.commit()
        await session.refresh(candidate)

    with pytest.raises(ValueError, match="остаток"):
        await ChannelImportService.approve_candidate(1, candidate.id)
