from __future__ import annotations

import asyncio
import logging
import random
import socket
from datetime import datetime, timedelta, timezone

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import or_, select

from app.database.db import async_session
from app.models.channel_import import (
    ChannelConnection,
    ChannelPost,
    ChannelPostButtonJob,
    ProductSourceRef,
)
from app.models.product import Product
from app.models.shop import Shop
from app.services.channel_post_button_service import (
    ChannelPostButtonService,
    product_deep_link,
    strip_managed_product_buttons,
)
from app.services.channel_attribution_service import ChannelAttributionService


logger = logging.getLogger(__name__)
RETRY_DELAYS = (5, 30, 120, 600, 1800)
CLAIMABLE_STATUSES = {"queued", "retry_wait", "processing"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PermanentButtonSyncError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ChannelPostButtonWorker:
    def __init__(self, *, concurrency: int = 1):
        self.concurrency = concurrency
        self.worker_id = f"{socket.gethostname()}:{id(self)}"

    async def run_forever(self) -> None:
        workers = [asyncio.create_task(self._worker_loop(index)) for index in range(self.concurrency)]
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
                logger.exception("Channel product-button worker loop failed")
                await asyncio.sleep(2)

    async def claim_job(self, lock_owner: str) -> int | None:
        now = _utcnow()
        async with async_session() as session:
            job = (
                await session.execute(
                    select(ChannelPostButtonJob)
                    .where(
                        ChannelPostButtonJob.status.in_(CLAIMABLE_STATUSES),
                        ChannelPostButtonJob.available_at <= now,
                        or_(
                            ChannelPostButtonJob.locked_until.is_(None),
                            ChannelPostButtonJob.locked_until < now,
                        ),
                    )
                    .order_by(ChannelPostButtonJob.available_at, ChannelPostButtonJob.id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if job is None:
                return None
            job.status = "processing"
            job.locked_by = lock_owner
            job.locked_until = now + timedelta(seconds=45)
            await session.commit()
            return job.id

    async def process_job(self, job_id: int) -> None:
        try:
            async with asyncio.timeout(30):
                await self._process_job(job_id)
        except PermanentButtonSyncError as exc:
            await self._mark_needs_action(job_id, exc.code, str(exc))
        except Exception as exc:
            await self._fail_or_retry(job_id, exc)

    async def _process_job(self, job_id: int) -> None:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(ChannelPostButtonJob, ChannelPost, ChannelConnection, Shop)
                    .join(ChannelPost, ChannelPost.id == ChannelPostButtonJob.post_id)
                    .join(ChannelConnection, ChannelConnection.id == ChannelPost.connection_id)
                    .join(Shop, Shop.id == ChannelPost.shop_id)
                    .where(ChannelPostButtonJob.id == job_id)
                )
            ).one_or_none()
            if row is None:
                return
            job, post, connection, shop = row
            if job.button_version != post.button_version:
                job.status = "superseded"
                job.locked_by = None
                job.locked_until = None
                await session.commit()
                return
            if not ChannelPostButtonService.enabled_for_shop(job.shop_id):
                raise PermanentButtonSyncError(
                    "feature_disabled", "Кнопки товаров выключены для магазина"
                )
            if not post.source_reply_markup_known:
                raise PermanentButtonSyncError(
                    "source_markup_unknown",
                    "Нельзя безопасно изменить старый пост: исходные кнопки неизвестны",
                )

            products = (
                await session.execute(
                    select(ProductSourceRef, Product)
                    .join(Product, Product.id == ProductSourceRef.product_id)
                    .where(
                        ProductSourceRef.shop_id == post.shop_id,
                        ProductSourceRef.connection_id == post.connection_id,
                        ProductSourceRef.telegram_message_id == post.telegram_message_id,
                        Product.is_active.is_(True),
                    )
                    .order_by(ProductSourceRef.candidate_position, ProductSourceRef.id)
                )
            ).all()
            source_markup = strip_managed_product_buttons(post.source_reply_markup)
            chat_id = connection.channel_id
            message_id = post.telegram_message_id
            shop_id = post.shop_id
            stored_username = shop.bot_username

        from app.bot.bot import get_bot

        bot = get_bot(shop_id)
        if bot is None:
            raise RuntimeError("Бот магазина временно недоступен")
        me = await bot.get_me()
        bot_username = me.username or stored_username
        if not bot_username:
            raise PermanentButtonSyncError("bot_username_missing", "У бота нет username")
        if not me.has_main_web_app:
            raise PermanentButtonSyncError(
                "main_app_missing", "Настройте Main Mini App для бота через BotFather"
            )

        try:
            member = await bot.get_chat_member(chat_id, me.id)
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            raise PermanentButtonSyncError(
                "channel_access_denied", "Бот больше не имеет доступа к каналу"
            ) from exc
        if member.status not in {"administrator", "creator"}:
            raise PermanentButtonSyncError(
                "channel_admin_required", "Бот должен быть администратором канала"
            )
        if member.status == "administrator" and not getattr(member, "can_edit_messages", False):
            raise PermanentButtonSyncError(
                "edit_permission_required",
                "Выдайте боту право редактировать публикации канала",
            )

        rows = list((source_markup or {}).get("inline_keyboard", []))
        for _ref, product in products:
            label = (
                "🛍 Открыть товар"
                if len(products) == 1
                else f"🛍 {product.name.strip()}"
            )
            if len(label) > 64:
                label = f"{label[:61].rstrip()}…"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        url=product_deep_link(
                            bot_username,
                            shop_id,
                            product.id,
                            _ref.public_token
                            if ChannelAttributionService.enabled_for_shop(shop_id)
                            else None,
                        ),
                        style="success",
                    ).model_dump(mode="json", exclude_none=True)
                ]
            )
        markup = InlineKeyboardMarkup.model_validate({"inline_keyboard": rows}) if rows else None

        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=markup,
            )
        except TelegramForbiddenError as exc:
            raise PermanentButtonSyncError(
                "channel_access_denied", "Telegram запретил изменять публикацию канала"
            ) from exc
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).casefold():
                message = str(exc)
                lowered = message.casefold()
                if any(
                    fragment in lowered
                    for fragment in (
                        "message to edit not found",
                        "message can't be edited",
                        "not enough rights",
                        "chat not found",
                    )
                ):
                    raise PermanentButtonSyncError("telegram_rejected", message) from exc
                raise

        async with async_session() as session:
            job = await session.get(ChannelPostButtonJob, job_id)
            if job is None:
                return
            current_post = await session.get(ChannelPost, job.post_id)
            if current_post and current_post.button_version != job.button_version:
                job.status = "superseded"
            else:
                job.status = "completed"
                job.completed_at = _utcnow()
                job.error_code = None
                job.last_error = None
            job.locked_by = None
            job.locked_until = None
            await session.commit()
        logger.info(
            "Channel product buttons synced job=%d shop=%d post=%d version=%d",
            job_id,
            shop_id,
            message_id,
            job.button_version,
        )

    async def _mark_needs_action(self, job_id: int, code: str, message: str) -> None:
        async with async_session() as session:
            job = await session.get(ChannelPostButtonJob, job_id)
            if job is None:
                return
            job.status = "needs_action"
            job.error_code = code
            job.last_error = message[:4000]
            job.locked_by = None
            job.locked_until = None
            await session.commit()
        logger.warning("Channel product buttons need action job=%d code=%s: %s", job_id, code, message)

    async def _fail_or_retry(self, job_id: int, exc: Exception) -> None:
        async with async_session() as session:
            job = await session.get(ChannelPostButtonJob, job_id)
            if job is None:
                return
            job.attempts += 1
            job.error_code = "temporary_telegram_error"
            job.last_error = str(exc)[:4000]
            job.locked_by = None
            job.locked_until = None
            if job.attempts > len(RETRY_DELAYS):
                job.status = "needs_action"
                job.error_code = "retry_exhausted"
            else:
                if isinstance(exc, TelegramRetryAfter):
                    delay = max(float(exc.retry_after), RETRY_DELAYS[job.attempts - 1])
                else:
                    delay = RETRY_DELAYS[job.attempts - 1]
                job.status = "retry_wait"
                job.available_at = _utcnow() + timedelta(
                    seconds=delay + random.uniform(0, 2)
                )
            await session.commit()
        logger.warning("Channel product-button job %d failed: %s", job_id, exc)
