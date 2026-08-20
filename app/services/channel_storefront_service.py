from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.database.db import async_session
from app.models.channel_import import ChannelConnection
from app.models.shop import Shop
from app.services.channel_post_button_service import ChannelPostButtonService, shop_deep_link
from app.utils.escape import esc


logger = logging.getLogger(__name__)
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StorefrontSyncError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ChannelStorefrontService:
    @staticmethod
    def enabled_for_shop(shop_id: int) -> bool:
        return ChannelPostButtonService.enabled_for_shop(shop_id)

    @staticmethod
    async def status(shop_id: int) -> dict:
        async with async_session() as session:
            connection = (
                await session.execute(
                    select(ChannelConnection).where(ChannelConnection.shop_id == shop_id)
                )
            ).scalar_one_or_none()
        if connection is None:
            raise ValueError("Канал ещё не подключён")
        return ChannelStorefrontService._status_dict(connection)

    @staticmethod
    async def sync(shop_id: int, *, bot: Bot | None = None) -> dict:
        if not ChannelStorefrontService.enabled_for_shop(shop_id):
            raise ValueError("Закреплённая кнопка пока не включена для этого магазина")
        async with _locks[shop_id]:
            await ChannelStorefrontService._set_state(
                shop_id,
                status="syncing",
                error_code=None,
                error=None,
            )
            try:
                await ChannelStorefrontService._sync(shop_id, bot=bot)
            except StorefrontSyncError as exc:
                await ChannelStorefrontService._set_state(
                    shop_id,
                    status="needs_action",
                    error_code=exc.code,
                    error=str(exc),
                )
                logger.warning(
                    "Channel storefront needs action shop=%d code=%s: %s",
                    shop_id,
                    exc.code,
                    exc,
                )
                raise ValueError(str(exc)) from exc
            except Exception as exc:
                await ChannelStorefrontService._set_state(
                    shop_id,
                    status="needs_action",
                    error_code="temporary_telegram_error",
                    error=str(exc)[:4000] or exc.__class__.__name__,
                )
                logger.exception("Channel storefront sync failed shop=%d", shop_id)
                raise RuntimeError(
                    "Telegram временно недоступен. Повторите установку закрепления."
                ) from exc
            return await ChannelStorefrontService.status(shop_id)

    @staticmethod
    async def _sync(shop_id: int, *, bot: Bot | None) -> None:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(ChannelConnection, Shop)
                    .join(Shop, Shop.id == ChannelConnection.shop_id)
                    .where(
                        ChannelConnection.shop_id == shop_id,
                        ChannelConnection.is_active.is_(True),
                    )
                )
            ).one_or_none()
        if row is None:
            raise StorefrontSyncError("channel_missing", "Канал ещё не подключён")
        connection, shop = row

        if bot is None:
            from app.bot.bot import get_bot

            bot = get_bot(shop_id)
        if bot is None:
            raise StorefrontSyncError("bot_unavailable", "Бот магазина временно недоступен")

        async with asyncio.timeout(20):
            me = await bot.get_me()
            if not me.has_main_web_app:
                raise StorefrontSyncError(
                    "main_app_missing", "Настройте Main Mini App для бота через BotFather"
                )
            bot_username = me.username or shop.bot_username
            if not bot_username:
                raise StorefrontSyncError("bot_username_missing", "У бота нет username")

            try:
                member = await bot.get_chat_member(connection.channel_id, me.id)
            except (TelegramForbiddenError, TelegramBadRequest) as exc:
                raise StorefrontSyncError(
                    "channel_access_denied", "Бот больше не имеет доступа к каналу"
                ) from exc
            if member.status not in {"administrator", "creator"}:
                raise StorefrontSyncError(
                    "channel_admin_required", "Бот должен быть администратором канала"
                )
            if member.status == "administrator" and not getattr(
                member, "can_edit_messages", False
            ):
                raise StorefrontSyncError(
                    "edit_permission_required",
                    "Выдайте боту право редактировать и закреплять публикации канала",
                )

            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🛍 Открыть магазин",
                            url=shop_deep_link(bot_username, shop_id),
                            style="success",
                        )
                    ]
                ]
            )
            text = (
                f"🛍 {esc(shop.name)}\n\n"
                "Откройте каталог магазина, чтобы посмотреть товары и оформить заказ."
            )
            message_id = connection.storefront_message_id
            if message_id is not None:
                try:
                    await bot.edit_message_text(
                        chat_id=connection.channel_id,
                        message_id=message_id,
                        text=text,
                        reply_markup=markup,
                    )
                except TelegramBadRequest as exc:
                    lowered = str(exc).casefold()
                    if "message is not modified" not in lowered:
                        if any(
                            fragment in lowered
                            for fragment in (
                                "message to edit not found",
                                "message can't be edited",
                            )
                        ):
                            message_id = None
                        else:
                            raise

            if message_id is None:
                sent = await bot.send_message(
                    chat_id=connection.channel_id,
                    text=text,
                    reply_markup=markup,
                    disable_notification=True,
                )
                message_id = sent.message_id
                await ChannelStorefrontService._set_message_id(shop_id, message_id)

            try:
                await bot.pin_chat_message(
                    chat_id=connection.channel_id,
                    message_id=message_id,
                    disable_notification=True,
                )
            except TelegramForbiddenError as exc:
                raise StorefrontSyncError(
                    "pin_permission_required",
                    "Telegram запретил закрепить сообщение. Проверьте права бота.",
                ) from exc

        await ChannelStorefrontService._set_state(
            shop_id,
            status="active",
            error_code=None,
            error=None,
        )
        logger.info(
            "Channel storefront synced shop=%d channel=%d message=%d",
            shop_id,
            connection.channel_id,
            message_id,
        )

    @staticmethod
    async def _set_message_id(shop_id: int, message_id: int) -> None:
        async with async_session() as session:
            connection = (
                await session.execute(
                    select(ChannelConnection)
                    .where(ChannelConnection.shop_id == shop_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if connection is None:
                raise StorefrontSyncError("channel_missing", "Канал ещё не подключён")
            connection.storefront_message_id = message_id
            connection.storefront_updated_at = _utcnow()
            await session.commit()

    @staticmethod
    async def _set_state(
        shop_id: int,
        *,
        status: str,
        error_code: str | None,
        error: str | None,
    ) -> None:
        async with async_session() as session:
            connection = (
                await session.execute(
                    select(ChannelConnection)
                    .where(ChannelConnection.shop_id == shop_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if connection is None:
                if status == "syncing":
                    raise ValueError("Канал ещё не подключён")
                return
            connection.storefront_status = status
            connection.storefront_error_code = error_code
            connection.storefront_error = error
            connection.storefront_updated_at = _utcnow()
            await session.commit()

    @staticmethod
    def _status_dict(connection: ChannelConnection) -> dict:
        return {
            "message_id": connection.storefront_message_id,
            "status": connection.storefront_status,
            "error_code": connection.storefront_error_code,
            "error": connection.storefront_error,
            "updated_at": (
                connection.storefront_updated_at.isoformat()
                if connection.storefront_updated_at
                else None
            ),
        }
