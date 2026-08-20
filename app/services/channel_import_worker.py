from __future__ import annotations

import asyncio
import logging
import random
import socket
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, or_, select

from app.core.config import settings
from app.database.db import async_session
from app.models.channel_import import (
    CatalogAnalysisRun,
    CatalogImportCandidate,
    CatalogImportJob,
    ChannelPost,
    ChannelPostMedia,
    PrefilterFeedback,
)
from app.models.shop import Shop
from app.services.channel_ai_service import ChannelAIService, PROMPT_VERSION
from app.services.channel_import_service import ChannelImportService, product_fingerprint
from app.utils.escape import esc
from app.services.channel_prefilter import PREFILTER_VERSION, classify_post
from app.services.subscription_service import SubscriptionService


logger = logging.getLogger(__name__)
RETRY_DELAYS = (5, 30, 120)
_shop_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_budget_warnings: set[tuple[int, int, int]] = set()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ChannelImportWorker:
    def __init__(self, *, ai_service: ChannelAIService | None = None, concurrency: int = 2):
        self.ai_service = ai_service or ChannelAIService()
        self.concurrency = concurrency
        self.worker_id = f"{socket.gethostname()}:{id(self)}"

    async def run_forever(self) -> None:
        workers = [asyncio.create_task(self._worker_loop(i)) for i in range(self.concurrency)]
        try:
            await asyncio.gather(*workers)
        finally:
            for worker in workers:
                worker.cancel()

    async def _worker_loop(self, index: int) -> None:
        while True:
            try:
                job_id = await self.claim_job(f"{self.worker_id}:{index}")
                if job_id is None:
                    await asyncio.sleep(1.5)
                    continue
                await self.process_job(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("AI-import worker loop failed")
                await asyncio.sleep(2)

    async def claim_job(self, lock_owner: str) -> int | None:
        now = _utcnow()
        async with async_session() as session:
            query = (
                select(CatalogImportJob)
                .where(
                    CatalogImportJob.status == "queued",
                    CatalogImportJob.available_at <= now,
                    or_(CatalogImportJob.locked_until.is_(None), CatalogImportJob.locked_until < now),
                )
                .order_by(CatalogImportJob.available_at, CatalogImportJob.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job = (await session.execute(query)).scalar_one_or_none()
            if job is None:
                return None
            job.status = "analyzing"
            job.locked_by = lock_owner
            job.locked_until = now + timedelta(seconds=60)
            await session.commit()
            return job.id

    async def process_job(self, job_id: int) -> None:
        async with async_session() as session:
            job = await session.get(CatalogImportJob, job_id)
            if job is None:
                return
            shop_id = job.shop_id

        async with _shop_locks[shop_id]:
            try:
                async with asyncio.timeout(45):
                    candidate_ids = await self._process_job(job_id)
                await self._maybe_warn_budget(shop_id)
                for candidate_id in candidate_ids:
                    await self._notify_candidate(shop_id, candidate_id)
            except Exception as exc:
                await self._fail_or_retry(job_id, exc)

    async def _process_job(self, job_id: int) -> list[int]:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(CatalogImportJob, ChannelPost)
                    .join(ChannelPost, CatalogImportJob.post_id == ChannelPost.id)
                    .where(CatalogImportJob.id == job_id)
                )
            ).one_or_none()
            if row is None:
                return []
            job, post = row
            if post.version != job.post_version:
                job.status = "superseded"
                await session.commit()
                return []
            if not await SubscriptionService.is_shop_active(job.shop_id):
                job.status = "subscription_blocked"
                job.locked_by = None
                job.locked_until = None
                post.status = "subscription_blocked"
                await session.commit()
                return []
            media_count = (
                await session.execute(
                    select(func.count()).select_from(ChannelPostMedia).where(
                        ChannelPostMedia.post_id == post.id
                    )
                )
            ).scalar_one()

            decision = classify_post(post.text, has_photos=media_count > 0)
            session.add(
                CatalogAnalysisRun(
                    shop_id=job.shop_id,
                    job_id=job.id,
                    run_type="prefilter",
                    prefilter_version=PREFILTER_VERSION,
                    result=decision.to_dict(),
                )
            )
            feedback = (
                await session.execute(
                    select(PrefilterFeedback).where(PrefilterFeedback.post_id == post.id)
                )
            ).scalar_one_or_none()
            if feedback is None:
                feedback = PrefilterFeedback(
                    shop_id=job.shop_id,
                    post_id=post.id,
                    prefilter_label=decision.label,
                    prefilter_confidence=decision.confidence,
                    features=decision.features,
                )
                session.add(feedback)
            else:
                feedback.prefilter_label = decision.label
                feedback.prefilter_confidence = decision.confidence
                feedback.features = decision.features

            if decision.label == "non_product":
                job.status = "completed"
                job.locked_by = None
                job.locked_until = None
                post.status = "non_product"
                await session.commit()
                return []
            if decision.label == "needs_manual":
                candidate = CatalogImportCandidate(
                    shop_id=job.shop_id,
                    job_id=job.id,
                    position=0,
                    status="needs_manual",
                    variants=[],
                    attributes={},
                    field_confidence={},
                )
                session.add(candidate)
                job.status = "completed"
                post.status = "needs_manual"
                job.locked_by = None
                job.locked_until = None
                await session.commit()
                await session.refresh(candidate)
                return [candidate.id]

            used_microusd = await self._monthly_cost(session)
            budget_microusd = int(settings.channel_import_budget_usd * 1_000_000)
            if used_microusd >= budget_microusd:
                job.status = "budget_blocked"
                job.locked_by = None
                job.locked_until = None
                post.status = "budget_blocked"
                await session.commit()
                return []

            text = post.text or ""
            shop_id = job.shop_id
            await session.commit()

        categories, attrs = await ChannelImportService.get_catalog_context(shop_id)
        analysis, usage = await self.ai_service.analyze_post(
            text,
            categories=categories,
            attribute_definitions=attrs,
        )

        async with async_session() as session:
            job = await session.get(CatalogImportJob, job_id)
            assert job is not None
            post = await session.get(ChannelPost, job.post_id)
            assert post is not None
            session.add(
                CatalogAnalysisRun(
                    shop_id=job.shop_id,
                    job_id=job.id,
                    run_type="cloud_ai",
                    prefilter_version=PREFILTER_VERSION,
                    prompt_version=PROMPT_VERSION,
                    model=settings.openai_model,
                    result=analysis.model_dump(),
                    **usage,
                )
            )
            if analysis.classification == "non_product":
                job.status = "completed"
                job.locked_by = None
                job.locked_until = None
                post.status = "non_product"
                await session.commit()
                return []
            await session.commit()

        products = analysis.products
        if not products:
            products = []

        created_ids: list[int] = []
        if not products:
            async with async_session() as session:
                job = await session.get(CatalogImportJob, job_id)
                assert job is not None
                post = await session.get(ChannelPost, job.post_id)
                candidate = CatalogImportCandidate(
                    shop_id=job.shop_id,
                    job_id=job.id,
                    position=0,
                    status="needs_manual",
                    variants=[],
                    attributes={},
                    field_confidence={},
                )
                session.add(candidate)
                job.status = "completed"
                job.locked_by = None
                job.locked_until = None
                post.status = "needs_manual"
                await session.commit()
                await session.refresh(candidate)
                return [candidate.id]

        prepared: list[dict] = []
        for position, product in enumerate(products):
            product_data = product.to_catalog_dict()
            matches = await ChannelImportService.find_duplicates(shop_id, product_data)
            best = matches[0] if matches else None
            score = float(best["score"]) if best else 0.0
            duplicate_id = int(best["product_id"]) if best else None
            duplicate_analysis = None
            duplicate_usage = None
            if score >= 0.92:
                status = "duplicate_skipped"
            elif score >= 0.75:
                status = "possible_duplicate"
                duplicate_decision, duplicate_usage = await self.ai_service.check_duplicate(
                    product, matches
                )
                duplicate_analysis = duplicate_decision.model_dump()
                if duplicate_decision.duplicate_product_id and duplicate_decision.confidence >= 0.92:
                    duplicate_id = duplicate_decision.duplicate_product_id
                    score = duplicate_decision.confidence
                    status = "duplicate_skipped"
            else:
                incomplete = (
                    not product.name
                    or not product.category_name
                    or not product.variants
                    or any(v.price is None or v.stock is None for v in product.variants)
                    or any(v.currency.upper() not in {"RUB", "RUR", "₽"} for v in product.variants)
                )
                status = "needs_manual" if incomplete else "pending"
            prepared.append(
                {
                    "position": position,
                    "status": status,
                    "product": product_data,
                    "duplicate_id": duplicate_id,
                    "duplicate_score": score if best else None,
                    "duplicate_analysis": duplicate_analysis,
                    "duplicate_usage": duplicate_usage,
                }
            )

        async with async_session() as session:
            job = await session.get(CatalogImportJob, job_id)
            assert job is not None
            post = await session.get(ChannelPost, job.post_id)
            assert post is not None
            for item in prepared:
                product = item["product"]
                variants = product.get("variants") or []
                currency = variants[0].get("currency", "RUB") if variants else "RUB"
                candidate = CatalogImportCandidate(
                    shop_id=job.shop_id,
                    job_id=job.id,
                    position=item["position"],
                    status=item["status"],
                    name=product.get("name"),
                    description=product.get("description"),
                    category_name=product.get("category_name"),
                    proposed_category=product.get("category_is_new", False),
                    sku=product.get("sku"),
                    currency=currency,
                    variants=variants,
                    attributes=product.get("attributes") or {},
                    field_confidence=product.get("field_confidence") or {},
                    fingerprint=product_fingerprint(product.get("name"), product.get("sku"), variants),
                    duplicate_product_id=item["duplicate_id"],
                    duplicate_score=item["duplicate_score"],
                )
                session.add(candidate)
                await session.flush()
                created_ids.append(candidate.id)
                if item.get("duplicate_analysis"):
                    session.add(
                        CatalogAnalysisRun(
                            shop_id=job.shop_id,
                            job_id=job.id,
                            run_type="duplicate_ai",
                            prompt_version=PROMPT_VERSION,
                            model=settings.openai_model,
                            result=item["duplicate_analysis"],
                            **item["duplicate_usage"],
                        )
                    )
            job.status = "completed"
            job.locked_by = None
            job.locked_until = None
            post.status = "drafted"
            await session.commit()
        return created_ids

    async def _monthly_cost(self, session) -> int:
        month_start = _utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return int(
            (
                await session.execute(
                    select(func.coalesce(func.sum(CatalogAnalysisRun.cost_microusd), 0)).where(
                        CatalogAnalysisRun.created_at >= month_start
                    )
                )
            ).scalar_one()
        )

    async def _fail_or_retry(self, job_id: int, exc: Exception) -> None:
        async with async_session() as session:
            job = await session.get(CatalogImportJob, job_id)
            if job is None:
                return
            job.attempts += 1
            job.last_error = str(exc)[:4000]
            job.locked_by = None
            job.locked_until = None
            session.add(
                CatalogAnalysisRun(
                    shop_id=job.shop_id,
                    job_id=job.id,
                    run_type="error",
                    prefilter_version=PREFILTER_VERSION,
                    prompt_version=PROMPT_VERSION,
                    model=settings.openai_model,
                    error=str(exc)[:4000],
                )
            )
            if job.attempts > len(RETRY_DELAYS):
                job.status = "failed"
            else:
                delay = RETRY_DELAYS[job.attempts - 1] + random.uniform(0, 2)
                job.status = "queued"
                job.available_at = _utcnow() + timedelta(seconds=delay)
            await session.commit()
        logger.warning("AI-import job %d failed: %s", job_id, exc)

    async def _maybe_warn_budget(self, shop_id: int) -> None:
        now = _utcnow()
        key = (shop_id, now.year, now.month)
        if key in _budget_warnings:
            return
        async with async_session() as session:
            used = await self._monthly_cost(session)
            shop = await session.get(Shop, shop_id)
        budget = int(settings.channel_import_budget_usd * 1_000_000)
        if not budget or used < budget * 0.8 or shop is None:
            return
        _budget_warnings.add(key)
        from app.bot.bot import get_bot

        bot = get_bot(shop_id)
        if bot:
            try:
                await bot.send_message(
                    shop.owner_telegram_id,
                    "⚠️ AI-импорт использовал 80% месячного бюджета. "
                    "При достижении лимита новые посты сохранятся в очереди.",
                )
            except Exception:
                logger.exception("Не удалось отправить предупреждение AI-бюджета")

    async def _notify_candidate(self, shop_id: int, candidate_id: int) -> None:
        candidate = await ChannelImportService.get_candidate(shop_id, candidate_id)
        if candidate is None:
            return
        async with async_session() as session:
            shop = await session.get(Shop, shop_id)
            connection = (
                await session.execute(
                    select(ChannelPost, CatalogImportJob)
                    .join(CatalogImportJob, CatalogImportJob.post_id == ChannelPost.id)
                    .where(CatalogImportJob.id == candidate["job_id"])
                )
            ).one_or_none()
            if shop is None or connection is None:
                return
            from app.models.channel_import import ChannelConnection

            channel_connection = await session.get(ChannelConnection, connection[0].connection_id)
            if channel_connection is None or not channel_connection.notifications_enabled:
                return
            owner_id = shop.owner_telegram_id

        from app.bot.bot import get_bot

        bot = get_bot(shop_id)
        if bot is None:
            return
        buttons = []
        if settings.admin_panel_url:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text="Открыть",
                        url=f"{settings.admin_panel_url.rstrip('/')}/channel-import?candidate={candidate_id}",
                    )
                ]
            )
        buttons.extend(
            [
                [InlineKeyboardButton(text="Подтвердить", callback_data=f"ci:approve:{candidate_id}")],
                [
                    InlineKeyboardButton(text="Не товар", callback_data=f"ci:reject:{candidate_id}"),
                    InlineKeyboardButton(text="Это дубликат", callback_data=f"ci:duplicate:{candidate_id}"),
                ],
            ]
        )
        try:
            await bot.send_message(
                owner_id,
                "🧠 <b>Новый AI-черновик</b>\n\n"
                f"{esc(candidate.get('name') or 'Нужно заполнить вручную')}\n"
                f"Статус: <code>{esc(candidate['status'])}</code>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            )
        except Exception:
            logger.exception("Не удалось уведомить владельца о черновике %d", candidate_id)
