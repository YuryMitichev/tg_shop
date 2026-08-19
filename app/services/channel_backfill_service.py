from __future__ import annotations

import logging
from datetime import datetime

from aiogram.types import BufferedInputFile

from app.core.config import settings
from app.database.db import async_session
from app.models.channel_import import ChannelConnection
from app.models.shop import Shop
from app.services.channel_import_service import ChannelImportService


logger = logging.getLogger(__name__)


def _naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


class ChannelBackfillService:
    @staticmethod
    async def backfill(connection_id: int, *, limit: int = 50) -> int:
        if not (settings.telegram_api_id and settings.telegram_api_hash and settings.telegram_session):
            raise RuntimeError(
                "Для backfill нужны TELEGRAM_API_ID, TELEGRAM_API_HASH и TELEGRAM_SESSION"
            )

        async with async_session() as session:
            connection = await session.get(ChannelConnection, connection_id)
            if connection is None:
                raise ValueError("Подключение канала не найдено")
            shop = await session.get(Shop, connection.shop_id)
            if shop is None:
                raise ValueError("Магазин не найден")
            connection.backfill_status = "running"
            connection.backfill_error = None
            await session.commit()
            shop_id = shop.id
            owner_id = shop.owner_telegram_id

        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(
            StringSession(settings.telegram_session),
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        imported = 0
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError("TELEGRAM_SESSION не авторизована")
            entity = await ChannelBackfillService._resolve_entity(client, connection)
            messages = list(await client.get_messages(entity, limit=limit))
            messages.reverse()

            grouped: dict[int, list] = {}
            singles: list[list] = []
            for message in messages:
                if message.grouped_id:
                    grouped.setdefault(int(message.grouped_id), []).append(message)
                else:
                    singles.append([message])
            batches = singles + list(grouped.values())
            batches.sort(key=lambda batch: min(message.id for message in batch))

            for batch in batches:
                root = min(batch, key=lambda message: message.id)
                text = next((message.message for message in batch if message.message), None)
                media: list[dict] = []
                for message in sorted(batch, key=lambda item: item.id):
                    if not message.photo:
                        continue
                    file_id = await ChannelBackfillService._convert_photo(
                        client, message, shop_id, owner_id
                    )
                    if file_id:
                        media.append({"file_id": file_id, "media_type": "photo"})
                await ChannelImportService.ingest_post(
                    shop_id,
                    telegram_message_id=root.id,
                    text=text,
                    media=media,
                    media_group_id=str(root.grouped_id) if root.grouped_id else None,
                    published_at=_naive(root.date),
                    edited_at=_naive(root.edit_date),
                    raw_data={"source": "telethon_backfill", "message_ids": [m.id for m in batch]},
                )
                imported += 1

            async with async_session() as session:
                current = await session.get(ChannelConnection, connection_id)
                if current:
                    current.backfill_status = "completed"
                    current.backfill_error = None
                    await session.commit()
            return imported
        except Exception as exc:
            async with async_session() as session:
                current = await session.get(ChannelConnection, connection_id)
                if current:
                    current.backfill_status = "failed"
                    current.backfill_error = str(exc)[:4000]
                    await session.commit()
            raise
        finally:
            await client.disconnect()

    @staticmethod
    async def _resolve_entity(client, connection: ChannelConnection):
        if connection.channel_username:
            return await client.get_entity(connection.channel_username)
        target_id = abs(connection.channel_id)
        if str(target_id).startswith("100"):
            target_id = int(str(target_id)[3:])
        async for dialog in client.iter_dialogs():
            if getattr(dialog.entity, "id", None) == target_id:
                return dialog.entity
        raise RuntimeError(
            "MTProto-аккаунт не видит канал. Добавьте его в канал или укажите username."
        )

    @staticmethod
    async def _convert_photo(client, message, shop_id: int, owner_id: int) -> str | None:
        from app.bot.bot import get_bot

        bot = get_bot(shop_id)
        if bot is None:
            raise RuntimeError("Бот магазина недоступен для конвертации исторического фото")
        photo_bytes = await client.download_media(message, file=bytes)
        if not photo_bytes:
            return None
        temporary = await bot.send_photo(
            owner_id,
            BufferedInputFile(photo_bytes, filename=f"channel-{message.id}.jpg"),
            disable_notification=True,
        )
        try:
            return temporary.photo[-1].file_id
        finally:
            await bot.delete_message(owner_id, temporary.message_id)
