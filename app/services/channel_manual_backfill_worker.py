from __future__ import annotations

import asyncio
import logging
import socket
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.database.db import async_session
from app.models.channel_import import (
    ChannelConnection,
    ChannelManualBackfillItem,
    ChannelManualBackfillSession,
)
from app.services.channel_import_service import ChannelImportService
from app.services.channel_manual_backfill_service import ChannelManualBackfillService


logger = logging.getLogger(__name__)
RETRY_DELAYS = (5, 30, 120)
CLAIMABLE_STATUSES = {"queued", "processing"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ChannelManualBackfillWorker:
    def __init__(self) -> None:
        self.worker_id = f"{socket.gethostname()}:{id(self)}"
        self._last_expiry_check = 0.0

    async def run_forever(self) -> None:
        while True:
            try:
                now_monotonic = asyncio.get_running_loop().time()
                if now_monotonic - self._last_expiry_check >= 60:
                    await ChannelManualBackfillService.expire_sessions()
                    self._last_expiry_check = now_monotonic
                session_id = await self.claim_session(self.worker_id)
                if session_id is None:
                    await asyncio.sleep(1.5)
                    continue
                await self.process_session(session_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Manual channel-backfill worker loop failed")
                await asyncio.sleep(2)

    async def claim_session(self, lock_owner: str) -> int | None:
        now = _utcnow()
        async with async_session() as session:
            backfill = (
                await session.execute(
                    select(ChannelManualBackfillSession)
                    .where(
                        ChannelManualBackfillSession.status.in_(CLAIMABLE_STATUSES),
                        ChannelManualBackfillSession.available_at <= now,
                        or_(
                            ChannelManualBackfillSession.locked_until.is_(None),
                            ChannelManualBackfillSession.locked_until < now,
                        ),
                    )
                    .order_by(
                        ChannelManualBackfillSession.available_at,
                        ChannelManualBackfillSession.id,
                    )
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if backfill is None:
                return None
            backfill.status = "processing"
            backfill.locked_by = lock_owner
            backfill.locked_until = now + timedelta(seconds=60)
            await session.commit()
            return backfill.id

    async def process_session(self, session_id: int) -> None:
        try:
            async with asyncio.timeout(60):
                imported, shop_id, owner_id = await self._process_session(session_id)
            await self._notify_completed(shop_id, owner_id, imported)
        except Exception as exc:
            await self._fail_or_retry(session_id, exc)

    async def _process_session(self, session_id: int) -> tuple[int, int, int]:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(ChannelManualBackfillSession, ChannelConnection)
                    .join(
                        ChannelConnection,
                        ChannelConnection.id
                        == ChannelManualBackfillSession.connection_id,
                    )
                    .where(ChannelManualBackfillSession.id == session_id)
                )
            ).one_or_none()
            if row is None:
                raise ValueError("Сессия импорта не найдена")
            backfill, connection = row
            items = (
                await session.execute(
                    select(ChannelManualBackfillItem)
                    .where(ChannelManualBackfillItem.session_id == session_id)
                    .order_by(ChannelManualBackfillItem.source_message_id)
                )
            ).scalars().all()
            shop_id = backfill.shop_id
            owner_id = backfill.owner_telegram_id

        grouped: OrderedDict[str, list[ChannelManualBackfillItem]] = OrderedDict()
        for item in items:
            grouped.setdefault(item.group_key, []).append(item)

        imported = 0
        for group_key, group in grouped.items():
            ordered = sorted(group, key=lambda item: item.source_message_id)
            root = ordered[0]
            text = next((item.text for item in ordered if item.text), None)
            media = [media for item in ordered for media in (item.media or [])]
            is_album = group_key.startswith("album:")
            await ChannelImportService.ingest_post(
                shop_id,
                telegram_message_id=root.source_message_id,
                text=text,
                media=media,
                media_group_id=(
                    f"manual:{session_id}:{group_key[6:]}"[:255]
                    if is_album
                    else None
                ),
                published_at=root.published_at,
                raw_data={
                    "source": "manual_forward_backfill",
                    "session_id": session_id,
                    "message_ids": [item.source_message_id for item in ordered],
                    "reply_markup_known": False,
                },
            )
            imported += 1

        now = _utcnow()
        async with async_session() as session:
            backfill = await session.get(ChannelManualBackfillSession, session_id)
            if backfill is None:
                raise ValueError("Сессия импорта исчезла")
            backfill.status = "completed"
            backfill.imported_publications = imported
            backfill.completed_at = now
            backfill.locked_by = None
            backfill.locked_until = None
            backfill.last_error = None
            connection = await session.get(ChannelConnection, backfill.connection_id)
            if connection:
                connection.backfill_status = "manual_completed"
                connection.backfill_error = None
            await session.commit()

        logger.info(
            "Manual channel backfill completed session=%d shop=%d publications=%d",
            session_id,
            shop_id,
            imported,
        )
        return imported, shop_id, owner_id

    async def _fail_or_retry(self, session_id: int, exc: Exception) -> None:
        async with async_session() as session:
            backfill = await session.get(ChannelManualBackfillSession, session_id)
            if backfill is None:
                return
            backfill.attempts += 1
            backfill.last_error = str(exc)[:4000]
            backfill.locked_by = None
            backfill.locked_until = None
            if backfill.attempts <= len(RETRY_DELAYS):
                backfill.status = "queued"
                backfill.available_at = _utcnow() + timedelta(
                    seconds=RETRY_DELAYS[backfill.attempts - 1]
                )
            else:
                backfill.status = "failed"
                backfill.completed_at = _utcnow()
                connection = await session.get(
                    ChannelConnection, backfill.connection_id
                )
                if connection:
                    connection.backfill_status = "manual_failed"
                    connection.backfill_error = backfill.last_error
            await session.commit()
        logger.warning(
            "Manual channel backfill failed session=%d attempt=%d: %s",
            session_id,
            backfill.attempts,
            exc,
        )

    async def _notify_completed(
        self, shop_id: int, owner_telegram_id: int, imported: int
    ) -> None:
        from app.bot.bot import get_bot

        bot = get_bot(shop_id)
        if bot is None:
            return
        try:
            await bot.send_message(
                owner_telegram_id,
                "✅ <b>Выбранные публикации переданы на обработку</b>\n\n"
                f"Публикаций: <b>{imported}</b>. AI создаст карточки или отправит "
                "сомнительные позиции на ручную проверку.",
                disable_notification=True,
            )
        except Exception:
            logger.exception(
                "Manual backfill completion notification failed shop=%d", shop_id
            )
