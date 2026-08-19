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
from app.services.channel_post_button_service import ChannelPostButtonService
from app.services.channel_storefront_service import ChannelStorefrontService
from app.services.channel_attribution_service import ChannelAttributionService
from app.services.channel_metrics_service import ChannelMetricsService


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


class ProductLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int


class ProductLinkUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int


class ButtonSyncRetry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_replace_unknown: bool = False


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
        "buttons_feature_enabled": (
            ChannelPostButtonService.enabled_for_shop(connection.shop_id)
            if connection
            else False
        ),
        "storefront_message_id": connection.storefront_message_id if connection else None,
        "storefront_status": connection.storefront_status if connection else "not_created",
        "storefront_error_code": connection.storefront_error_code if connection else None,
        "storefront_error": connection.storefront_error if connection else None,
    }


async def _button_readiness(shop_id: int, connection) -> dict:
    result = {
        "main_app_ready": None,
        "can_edit_messages": None,
        "buttons_ready": False,
        "buttons_error": None,
    }
    if connection is None or not ChannelPostButtonService.enabled_for_shop(shop_id):
        return result
    bot = get_bot(shop_id)
    if bot is None:
        result["buttons_error"] = "Бот магазина временно недоступен"
        return result
    try:
        async with asyncio.timeout(8):
            me = await bot.get_me()
            member = await bot.get_chat_member(connection.channel_id, me.id)
        result["main_app_ready"] = bool(me.has_main_web_app)
        result["can_edit_messages"] = (
            member.status == "creator"
            or (
                member.status == "administrator"
                and bool(getattr(member, "can_edit_messages", False))
            )
        )
        result["buttons_ready"] = bool(
            result["main_app_ready"] and result["can_edit_messages"]
        )
        if not result["main_app_ready"]:
            result["buttons_error"] = "Настройте Main Mini App через BotFather"
        elif not result["can_edit_messages"]:
            result["buttons_error"] = "Разрешите боту редактировать публикации канала"
    except Exception as exc:
        logger.warning("Button readiness check failed for shop_id=%d: %s", shop_id, exc)
        result["buttons_error"] = "Не удалось проверить настройки Telegram"
    return result


@router.get("/settings")
async def get_settings(admin: dict = Depends(require_admin)):
    connection = await ChannelImportService.get_connection(admin["shop_id"])
    result = _connection_dict(connection)
    if connection is None:
        result["feature_enabled"] = ChannelImportService.enabled_for_shop(admin["shop_id"])
        result["buttons_feature_enabled"] = ChannelPostButtonService.enabled_for_shop(
            admin["shop_id"]
        )
    result.update(await _button_readiness(admin["shop_id"], connection))
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


@router.post("/storefront-pin/sync")
async def sync_storefront_pin(
    admin: dict = Depends(require_active_subscription),
):
    try:
        return await ChannelStorefrontService.sync(admin["shop_id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/publication-analytics")
async def get_publication_analytics(admin: dict = Depends(require_admin)):
    return await ChannelAttributionService.publication_report(admin["shop_id"])


@router.post("/publication-analytics/views/refresh")
async def refresh_publication_views(
    admin: dict = Depends(require_active_subscription),
):
    try:
        updated = await ChannelMetricsService.refresh_shop(admin["shop_id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, "updated": updated}


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


@router.get("/product-options")
async def search_product_options(q: str, admin: dict = Depends(require_admin)):
    return await ChannelPostButtonService.search_products(admin["shop_id"], q)


@router.get("/posts/{post_id}/product-links")
async def get_product_links(post_id: int, admin: dict = Depends(require_admin)):
    try:
        return await ChannelPostButtonService.list_links(admin["shop_id"], post_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/posts/{post_id}/product-links")
async def add_product_link(
    post_id: int,
    body: ProductLinkCreate,
    admin: dict = Depends(require_active_subscription),
):
    try:
        return await ChannelPostButtonService.add_link(
            admin["shop_id"], post_id, body.product_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/posts/{post_id}/product-links/{link_id}")
async def replace_product_link(
    post_id: int,
    link_id: int,
    body: ProductLinkUpdate,
    admin: dict = Depends(require_active_subscription),
):
    try:
        return await ChannelPostButtonService.replace_link(
            admin["shop_id"], post_id, link_id, body.product_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/posts/{post_id}/product-links/{link_id}")
async def delete_product_link(
    post_id: int,
    link_id: int,
    admin: dict = Depends(require_active_subscription),
):
    try:
        return await ChannelPostButtonService.remove_link(
            admin["shop_id"], post_id, link_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/posts/{post_id}/button-sync/retry")
async def retry_button_sync(
    post_id: int,
    body: ButtonSyncRetry,
    admin: dict = Depends(require_active_subscription),
):
    try:
        return await ChannelPostButtonService.retry_post(
            admin["shop_id"],
            post_id,
            allow_replace_unknown=body.allow_replace_unknown,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
