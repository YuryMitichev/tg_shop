from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.database.db import async_session
from app.models.channel_import import ChannelConnection, ChannelPost, ProductSourceRef
from app.services.channel_attribution_service import ChannelAttributionService
from app.services.channel_backfill_service import ChannelBackfillService


logger = logging.getLogger(__name__)


class ChannelMetricsService:
    """Безопасно обновляет накопительные просмотры постов через MTProto."""

    @staticmethod
    async def refresh_shop(shop_id: int, *, limit: int = 100) -> int:
        if not ChannelAttributionService.enabled_for_shop(shop_id):
            raise ValueError("Аналитика публикаций не включена для магазина")
        if not (
            settings.telegram_api_id
            and settings.telegram_api_hash
            and settings.telegram_session
        ):
            raise RuntimeError("MTProto не настроен: просмотры Telegram недоступны")

        async with async_session() as session:
            connection = (
                await session.execute(
                    select(ChannelConnection).where(
                        ChannelConnection.shop_id == shop_id,
                        ChannelConnection.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if connection is None:
                raise ValueError("Канал не подключён")
            posts = (
                await session.execute(
                    select(ChannelPost)
                    .where(
                        ChannelPost.shop_id == shop_id,
                        select(ProductSourceRef.id)
                        .where(
                            ProductSourceRef.shop_id == shop_id,
                            ProductSourceRef.connection_id == ChannelPost.connection_id,
                            ProductSourceRef.telegram_message_id
                            == ChannelPost.telegram_message_id,
                        )
                        .exists(),
                    )
                    .order_by(ChannelPost.id.desc())
                    .limit(limit)
                )
            ).scalars().all()
            if not posts:
                return 0

        from telethon import TelegramClient, functions
        from telethon.sessions import StringSession

        client = TelegramClient(
            StringSession(settings.telegram_session),
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError("TELEGRAM_SESSION не авторизована")
            entity = await ChannelBackfillService._resolve_entity(client, connection)
            peer = await client.get_input_entity(entity)
            message_ids = [post.telegram_message_id for post in posts]
            response = await client(
                functions.messages.GetMessagesViewsRequest(
                    peer=peer,
                    id=message_ids,
                    increment=False,
                )
            )
            now = datetime.now()
            async with async_session() as session:
                for post, metric in zip(posts, response.views, strict=False):
                    current = await session.get(ChannelPost, post.id)
                    if current is None:
                        continue
                    current.telegram_views = getattr(metric, "views", None) or 0
                    current.telegram_forwards = getattr(metric, "forwards", None) or 0
                    current.metrics_updated_at = now
                await session.commit()
            logger.info(
                "Channel metrics refreshed shop=%d posts=%d", shop_id, len(posts)
            )
            return len(posts)
        finally:
            await client.disconnect()

    @staticmethod
    async def run_forever() -> None:
        while True:
            try:
                async with async_session() as session:
                    shop_ids = (
                        await session.execute(
                            select(ChannelConnection.shop_id).where(
                                ChannelConnection.is_active.is_(True)
                            )
                        )
                    ).scalars().all()
                for shop_id in shop_ids:
                    if not ChannelAttributionService.enabled_for_shop(shop_id):
                        continue
                    try:
                        await ChannelMetricsService.refresh_shop(shop_id)
                    except Exception:
                        logger.exception(
                            "Channel metrics refresh failed shop=%d; retry in next cycle",
                            shop_id,
                        )
            except Exception:
                logger.exception("Channel metrics loop failed")
            await asyncio.sleep(3600)
