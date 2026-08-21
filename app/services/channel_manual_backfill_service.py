from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.database.db import async_session
from app.models.channel_import import (
    ChannelConnection,
    ChannelManualBackfillItem,
    ChannelManualBackfillSession,
)
from app.models.shop import Shop
from app.services.channel_import_service import ChannelImportService
from app.utils.escape import esc


logger = logging.getLogger(__name__)
SESSION_TTL_MINUTES = 30
MAX_PUBLICATIONS = 50
MAX_SOURCE_MESSAGES = 500
ACTIVE_STATUSES = {"collecting", "queued", "processing"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _origin_type(origin) -> str | None:
    value = getattr(origin, "type", None)
    return getattr(value, "value", value)


def manual_backfill_markup(session_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Завершить выбор",
                    callback_data=f"cib:finish:{session_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отменить импорт",
                    callback_data=f"cib:cancel:{session_id}",
                )
            ],
        ]
    )


class ChannelManualBackfillService:
    @staticmethod
    async def create_session(shop_id: int, delivery_mode: str) -> tuple[int, str]:
        if delivery_mode not in {"browser", "phone"}:
            raise ValueError("Неизвестный способ открытия Telegram")
        if not ChannelImportService.enabled_for_shop(shop_id):
            raise ValueError("AI-импорт не включён для магазина")

        now = _utcnow()
        token = secrets.token_urlsafe(12)
        async with async_session() as session:
            connection = (
                await session.execute(
                    select(ChannelConnection).where(
                        ChannelConnection.shop_id == shop_id,
                        ChannelConnection.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
            shop = await session.get(Shop, shop_id)
            if connection is None:
                raise ValueError("Канал ещё не подключён")
            if connection.is_paused:
                raise ValueError("Импорт канала приостановлен")
            if shop is None or not shop.owner_telegram_id:
                raise ValueError("Владелец магазина не настроен")

            active = (
                await session.execute(
                    select(ChannelManualBackfillSession).where(
                        ChannelManualBackfillSession.shop_id == shop_id,
                        ChannelManualBackfillSession.status.in_(ACTIVE_STATUSES),
                    ).with_for_update()
                )
            ).scalars().all()
            if any(item.status in {"queued", "processing"} for item in active):
                raise ValueError("Предыдущие публикации уже обрабатываются")
            for item in active:
                item.status = "cancelled"
                item.completed_at = now
                item.locked_by = None
                item.locked_until = None

            backfill = ChannelManualBackfillSession(
                shop_id=shop_id,
                connection_id=connection.id,
                owner_telegram_id=shop.owner_telegram_id,
                token_hash=_token_hash(token),
                status="collecting",
                delivery_mode=delivery_mode,
                instruction_status="pending",
                requested_limit=MAX_PUBLICATIONS,
                available_at=now,
                expires_at=now + timedelta(minutes=SESSION_TTL_MINUTES),
            )
            session.add(backfill)
            connection.backfill_status = "manual_collecting"
            connection.backfill_error = None
            await session.commit()
            await session.refresh(backfill)
            return backfill.id, token

    @staticmethod
    async def session_for_token(
        shop_id: int, owner_telegram_id: int, token: str
    ) -> int | None:
        now = _utcnow()
        async with async_session() as session:
            backfill = (
                await session.execute(
                    select(ChannelManualBackfillSession).where(
                        ChannelManualBackfillSession.shop_id == shop_id,
                        ChannelManualBackfillSession.owner_telegram_id
                        == owner_telegram_id,
                        ChannelManualBackfillSession.token_hash == _token_hash(token),
                        ChannelManualBackfillSession.status == "collecting",
                        ChannelManualBackfillSession.expires_at > now,
                    )
                )
            ).scalar_one_or_none()
            return backfill.id if backfill else None

    @staticmethod
    async def deliver_instructions(session_id: int, bot) -> dict:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(ChannelManualBackfillSession, ChannelConnection, Shop)
                    .join(
                        ChannelConnection,
                        ChannelConnection.id
                        == ChannelManualBackfillSession.connection_id,
                    )
                    .join(Shop, Shop.id == ChannelManualBackfillSession.shop_id)
                    .where(ChannelManualBackfillSession.id == session_id)
                )
            ).one_or_none()
            if row is None:
                raise ValueError("Сессия импорта не найдена")
            backfill, connection, shop = row
            owner_id = backfill.owner_telegram_id
            channel_title = connection.channel_title
            stored_username = shop.bot_username

        bot_username = stored_username
        try:
            async with asyncio.timeout(10):
                me = await bot.get_me()
                bot_username = me.username or stored_username
                message = await bot.send_message(
                    owner_id,
                    ChannelManualBackfillService.instruction_text(channel_title, 0, 0),
                    reply_markup=manual_backfill_markup(session_id),
                    disable_notification=True,
                )
        except Exception as exc:
            async with async_session() as session:
                current = await session.get(ChannelManualBackfillSession, session_id)
                if current:
                    current.instruction_status = "failed"
                    current.last_error = str(exc)[:1000]
                    await session.commit()
            logger.warning(
                "Manual backfill instruction delivery failed shop=%s session=%s: %s",
                getattr(backfill, "shop_id", None),
                session_id,
                exc,
            )
            return {
                "instruction_sent": False,
                "bot_username": bot_username,
                "error": "Бот не смог отправить сообщение владельцу",
            }

        async with async_session() as session:
            current = await session.get(ChannelManualBackfillSession, session_id)
            if current:
                current.instruction_status = "sent"
                current.instruction_message_id = message.message_id
                current.last_error = None
                await session.commit()
        return {
            "instruction_sent": True,
            "bot_username": bot_username,
            "error": None,
        }

    @staticmethod
    async def refresh_instruction(session_id: int, bot) -> None:
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
                return
            backfill, connection = row
            if not backfill.instruction_message_id:
                return
            owner_id = backfill.owner_telegram_id
            instruction_message_id = backfill.instruction_message_id
            text = ChannelManualBackfillService.instruction_text(
                connection.channel_title,
                backfill.received_messages,
                backfill.received_publications,
            )
        try:
            await bot.edit_message_text(
                text,
                chat_id=owner_id,
                message_id=instruction_message_id,
                reply_markup=manual_backfill_markup(session_id),
            )
        except Exception as exc:
            if "message is not modified" not in str(exc).lower():
                logger.warning(
                    "Manual backfill progress update failed session=%d: %s",
                    session_id,
                    exc,
                )

    @staticmethod
    def instruction_text(
        channel_title: str, received_messages: int, received_publications: int
    ) -> str:
        progress = ""
        if received_messages:
            progress = (
                f"\n\nПолучено сообщений: <b>{received_messages}</b>\n"
                f"Найдено публикаций: <b>{received_publications}</b> из {MAX_PUBLICATIONS}"
            )
        return (
            "📥 <b>Добавление товаров из старых публикаций</b>\n\n"
            f"Канал: <b>{esc(channel_title)}</b>\n\n"
            "1. Откройте подключённый канал.\n"
            "2. Выберите публикации именно с теми товарами, которые хотите "
            "добавить в каталог.\n"
            "3. Перешлите их сюда. Можно отправить несколько партий — до 50 "
            "сообщений за один раз.\n"
            "4. Альбомы пересылайте целиком.\n"
            "5. Когда закончите, нажмите «Завершить выбор».\n\n"
            "Новости, отзывы и случайные публикации AI дополнительно отфильтрует."
            f"{progress}"
        )

    @staticmethod
    async def accept_forward(shop_id: int, owner_telegram_id: int, message: Message) -> dict | None:
        now = _utcnow()
        async with async_session() as session:
            backfill = (
                await session.execute(
                    select(ChannelManualBackfillSession)
                    .where(
                        ChannelManualBackfillSession.shop_id == shop_id,
                        ChannelManualBackfillSession.owner_telegram_id
                        == owner_telegram_id,
                        ChannelManualBackfillSession.status == "collecting",
                    )
                    .order_by(ChannelManualBackfillSession.id.desc())
                    .limit(1)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if backfill is None:
                return None
            if backfill.expires_at <= now:
                backfill.status = "expired"
                backfill.completed_at = now
                await session.commit()
                return {"accepted": False, "reason": "expired"}

            connection = await session.get(ChannelConnection, backfill.connection_id)
            origin = getattr(message, "forward_origin", None)
            origin_chat = getattr(origin, "chat", None)
            if (
                connection is None
                or _origin_type(origin) != "channel"
                or getattr(origin_chat, "id", None) != connection.channel_id
            ):
                backfill.rejected_messages += 1
                await session.commit()
                return {"accepted": False, "reason": "wrong_channel"}

            source_message_id = int(getattr(origin, "message_id", 0) or 0)
            if source_message_id <= 0:
                backfill.rejected_messages += 1
                await session.commit()
                return {"accepted": False, "reason": "missing_source_id"}

            existing = (
                await session.execute(
                    select(ChannelManualBackfillItem.id).where(
                        ChannelManualBackfillItem.session_id == backfill.id,
                        ChannelManualBackfillItem.source_message_id
                        == source_message_id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return {
                    "accepted": True,
                    "duplicate": True,
                    "session_id": backfill.id,
                    "received_messages": backfill.received_messages,
                    "received_publications": backfill.received_publications,
                }

            photo_data: list[dict] = []
            if message.photo:
                photo = message.photo[-1]
                photo_data.append(
                    {
                        "file_id": photo.file_id,
                        "file_unique_id": photo.file_unique_id,
                        "media_type": "photo",
                    }
                )
            text = message.caption or message.text
            if not text and not photo_data:
                backfill.rejected_messages += 1
                await session.commit()
                return {"accepted": False, "reason": "unsupported_content"}

            source_group = str(message.media_group_id) if message.media_group_id else None
            group_key = (
                f"album:{source_group}"
                if source_group
                else f"message:{source_message_id}"
            )
            known_group = (
                await session.execute(
                    select(ChannelManualBackfillItem.id).where(
                        ChannelManualBackfillItem.session_id == backfill.id,
                        ChannelManualBackfillItem.group_key == group_key,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if not known_group and backfill.received_publications >= backfill.requested_limit:
                backfill.rejected_messages += 1
                await session.commit()
                return {"accepted": False, "reason": "publication_limit"}
            if backfill.received_messages >= MAX_SOURCE_MESSAGES:
                backfill.rejected_messages += 1
                await session.commit()
                return {"accepted": False, "reason": "message_limit"}

            session.add(
                ChannelManualBackfillItem(
                    session_id=backfill.id,
                    source_message_id=source_message_id,
                    source_media_group_id=source_group,
                    group_key=group_key,
                    destination_message_id=message.message_id,
                    text=text,
                    media=photo_data,
                    published_at=_naive(getattr(origin, "date", None)),
                )
            )
            backfill.received_messages += 1
            if not known_group:
                backfill.received_publications += 1
            await session.commit()
            return {
                "accepted": True,
                "duplicate": False,
                "session_id": backfill.id,
                "received_messages": backfill.received_messages,
                "received_publications": backfill.received_publications,
            }

    @staticmethod
    async def queue_processing(
        shop_id: int, owner_telegram_id: int, session_id: int
    ) -> dict:
        now = _utcnow()
        async with async_session() as session:
            backfill = await session.get(ChannelManualBackfillSession, session_id)
            if (
                backfill is None
                or backfill.shop_id != shop_id
                or backfill.owner_telegram_id != owner_telegram_id
            ):
                raise ValueError("Сессия импорта не найдена")
            if backfill.status in {"queued", "processing", "completed"}:
                return ChannelManualBackfillService._payload(backfill)
            if backfill.status != "collecting":
                raise ValueError("Эта сессия импорта уже закрыта")
            if backfill.received_publications <= 0:
                raise ValueError("Сначала перешлите хотя бы одну публикацию с товаром")

            backfill.status = "queued"
            backfill.available_at = now + timedelta(seconds=3)
            backfill.locked_by = None
            backfill.locked_until = None
            connection = await session.get(ChannelConnection, backfill.connection_id)
            if connection:
                connection.backfill_status = "manual_processing"
                connection.backfill_error = None
            await session.commit()
            return ChannelManualBackfillService._payload(backfill)

    @staticmethod
    async def cancel(shop_id: int, owner_telegram_id: int, session_id: int) -> dict:
        async with async_session() as session:
            backfill = await session.get(ChannelManualBackfillSession, session_id)
            if (
                backfill is None
                or backfill.shop_id != shop_id
                or backfill.owner_telegram_id != owner_telegram_id
            ):
                raise ValueError("Сессия импорта не найдена")
            if backfill.status in {"processing", "completed"}:
                raise ValueError("Обработка уже началась, отменить её нельзя")
            if backfill.status not in {"cancelled", "expired", "failed"}:
                backfill.status = "cancelled"
                backfill.completed_at = _utcnow()
                backfill.locked_by = None
                backfill.locked_until = None
                await session.commit()
            return ChannelManualBackfillService._payload(backfill)

    @staticmethod
    async def latest(shop_id: int) -> dict | None:
        async with async_session() as session:
            backfill = (
                await session.execute(
                    select(ChannelManualBackfillSession)
                    .where(ChannelManualBackfillSession.shop_id == shop_id)
                    .order_by(ChannelManualBackfillSession.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return ChannelManualBackfillService._payload(backfill) if backfill else None

    @staticmethod
    async def expire_sessions() -> int:
        now = _utcnow()
        async with async_session() as session:
            expired = (
                await session.execute(
                    select(ChannelManualBackfillSession).where(
                        ChannelManualBackfillSession.status == "collecting",
                        ChannelManualBackfillSession.expires_at <= now,
                    )
                )
            ).scalars().all()
            connection_ids: set[int] = set()
            for backfill in expired:
                backfill.status = "expired"
                backfill.completed_at = now
                backfill.locked_by = None
                backfill.locked_until = None
                connection_ids.add(backfill.connection_id)
            if connection_ids:
                connections = (
                    await session.execute(
                        select(ChannelConnection).where(
                            ChannelConnection.id.in_(connection_ids)
                        )
                    )
                ).scalars().all()
                for connection in connections:
                    connection.backfill_status = "manual_expired"
            await session.commit()
            return len(expired)

    @staticmethod
    def _payload(backfill: ChannelManualBackfillSession) -> dict:
        return {
            "id": backfill.id,
            "status": backfill.status,
            "delivery_mode": backfill.delivery_mode,
            "instruction_status": backfill.instruction_status,
            "requested_limit": backfill.requested_limit,
            "received_messages": backfill.received_messages,
            "received_publications": backfill.received_publications,
            "rejected_messages": backfill.rejected_messages,
            "imported_publications": backfill.imported_publications,
            "expires_at": backfill.expires_at.isoformat() if backfill.expires_at else None,
            "completed_at": (
                backfill.completed_at.isoformat() if backfill.completed_at else None
            ),
            "last_error": backfill.last_error,
        }
