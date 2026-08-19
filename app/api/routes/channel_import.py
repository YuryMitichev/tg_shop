from __future__ import annotations

import asyncio
import logging
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.admin_auth import require_active_subscription, require_admin
from app.bot.bot import get_bot
from app.database.db import async_session
from app.models.channel_import import ChannelPost, ChannelPostMedia
from app.services.channel_import_service import ChannelImportService


router = APIRouter(prefix="/channel-import")
logger = logging.getLogger(__name__)


async def _run_backfill_safely(shop_id: int) -> None:
    try:
        await ChannelImportService.enqueue_backfill(shop_id)
    except Exception:
        logger.exception("Channel backfill failed for shop_id=%d", shop_id)


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_paused: bool | None = None
    notifications_enabled: bool | None = None


class CandidateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    description: str | None = None
    category_name: str | None = None
    proposed_category: bool | None = None
    sku: str | None = None
    currency: str | None = None
    variants: list[dict] | None = None
    attributes: dict | None = None
    owner_note: str | None = None


def _connection_dict(connection) -> dict:
    return {
        "connected": connection is not None,
        "feature_enabled": ChannelImportService.enabled_for_shop(connection.shop_id)
        if connection
        else False,
        "channel_id": connection.channel_id if connection else None,
        "channel_title": connection.channel_title if connection else None,
        "channel_username": connection.channel_username if connection else None,
        "is_active": connection.is_active if connection else False,
        "is_paused": connection.is_paused if connection else False,
        "notifications_enabled": connection.notifications_enabled if connection else True,
        "backfill_status": connection.backfill_status if connection else None,
        "backfill_error": connection.backfill_error if connection else None,
    }


@router.get("/settings")
async def get_settings(admin: dict = Depends(require_admin)):
    connection = await ChannelImportService.get_connection(admin["shop_id"])
    result = _connection_dict(connection)
    if connection is None:
        result["feature_enabled"] = ChannelImportService.enabled_for_shop(admin["shop_id"])
    return result


@router.put("/settings")
async def update_settings(
    body: SettingsUpdate, admin: dict = Depends(require_active_subscription)
):
    try:
        connection = await ChannelImportService.update_settings(
            admin["shop_id"],
            is_paused=body.is_paused,
            notifications_enabled=body.notifications_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _connection_dict(connection)


@router.post("/backfill")
async def run_backfill(admin: dict = Depends(require_active_subscription)):
    if not ChannelImportService.enabled_for_shop(admin["shop_id"]):
        raise HTTPException(status_code=403, detail="AI-импорт не включён для магазина")
    if not ChannelImportService.mtproto_configured():
        raise HTTPException(
            status_code=400,
            detail="Исторический импорт не настроен; realtime продолжает работать",
        )
    connection = await ChannelImportService.get_connection(admin["shop_id"])
    if connection is None:
        raise HTTPException(status_code=404, detail="Канал ещё не подключён")
    asyncio.create_task(_run_backfill_safely(admin["shop_id"]))
    return {"ok": True, "status": "started"}


@router.get("/candidates")
async def list_candidates(
    status: str | None = None, admin: dict = Depends(require_admin)
):
    return await ChannelImportService.list_candidates(admin["shop_id"], status=status)


@router.get("/candidates/{candidate_id}")
async def get_candidate(candidate_id: int, admin: dict = Depends(require_admin)):
    candidate = await ChannelImportService.get_candidate(admin["shop_id"], candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Черновик не найден")
    return candidate


@router.patch("/candidates/{candidate_id}")
async def update_candidate(
    candidate_id: int,
    body: CandidateUpdate,
    admin: dict = Depends(require_active_subscription),
):
    try:
        return await ChannelImportService.update_candidate(
            admin["shop_id"], candidate_id, body.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/candidates/{candidate_id}/approve")
async def approve_candidate(
    candidate_id: int, admin: dict = Depends(require_active_subscription)
):
    try:
        product_id = await ChannelImportService.approve_candidate(admin["shop_id"], candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "product_id": product_id}


@router.post("/candidates/{candidate_id}/reject")
async def reject_candidate(
    candidate_id: int, admin: dict = Depends(require_active_subscription)
):
    try:
        await ChannelImportService.set_candidate_status(
            admin["shop_id"], candidate_id, "rejected", "non_product"
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/candidates/{candidate_id}/mark-duplicate")
async def mark_duplicate(
    candidate_id: int, admin: dict = Depends(require_active_subscription)
):
    try:
        await ChannelImportService.set_candidate_status(
            admin["shop_id"], candidate_id, "duplicate_skipped", "duplicate"
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/candidates/{candidate_id}/reanalyze")
async def reanalyze_candidate(
    candidate_id: int, admin: dict = Depends(require_active_subscription)
):
    try:
        job_id = await ChannelImportService.reanalyze_candidate(admin["shop_id"], candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "job_id": job_id}


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: int, admin: dict = Depends(require_active_subscription)):
    try:
        await ChannelImportService.retry_job(admin["shop_id"], job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/stats")
async def get_stats(admin: dict = Depends(require_admin)):
    return await ChannelImportService.stats(admin["shop_id"])


@router.get("/media/{media_id}")
async def get_media(media_id: int, admin: dict = Depends(require_admin)):
    async with async_session() as session:
        media = (
            await session.execute(
                select(ChannelPostMedia)
                .join(ChannelPost, ChannelPostMedia.post_id == ChannelPost.id)
                .where(
                    ChannelPostMedia.id == media_id,
                    ChannelPost.shop_id == admin["shop_id"],
                )
            )
        ).scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Фото не найдено")
    bot = get_bot(admin["shop_id"])
    if bot is None:
        raise HTTPException(status_code=503, detail="Бот магазина недоступен")
    telegram_file = await bot.get_file(media.file_id)
    buffer = BytesIO()
    await bot.download_file(telegram_file.file_path, destination=buffer)
    return Response(content=buffer.getvalue(), media_type="image/jpeg")
