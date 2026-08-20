from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import re

import aiohttp
from sqlalchemy import select

from app.core.config import settings
from app.database.db import async_session
from app.models.channel_import import ChannelConnection, ChannelPost, ProductSourceRef
from app.services.channel_attribution_service import ChannelAttributionService
from app.services.channel_backfill_service import ChannelBackfillService


logger = logging.getLogger(__name__)

_PUBLIC_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
_PUBLIC_VIEWS_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*([KMB])?$", re.IGNORECASE)
_MAX_PUBLIC_HTML_BYTES = 512 * 1024
_MAX_TELEGRAM_VIEWS = 2_147_483_647
_PUBLIC_REFRESH_DEADLINE_SECONDS = 45


class _TelegramViewsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._capture_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._capture_depth:
            self._capture_depth += 1
            return
        classes = dict(attrs).get("class", "") or ""
        if "tgme_widget_message_views" in classes.split():
            self._capture_depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self._capture_depth:
            self._capture_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._capture_depth:
            self._parts.append(data)

    @property
    def views_text(self) -> str:
        return "".join(self._parts).strip()


def parse_public_views_html(document: str) -> int:
    """Извлекает views из официального Telegram embed без чтения содержимого поста."""
    parser = _TelegramViewsParser()
    parser.feed(document)
    value = parser.views_text.replace("\u00a0", "").replace(" ", "")
    match = _PUBLIC_VIEWS_RE.fullmatch(value)
    if match is None:
        raise ValueError("Telegram не вернул корректный счётчик просмотров")
    try:
        number = Decimal(match.group(1).replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("Некорректный формат счётчика Telegram") from exc
    multiplier = {None: 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[
        match.group(2).upper() if match.group(2) else None
    ]
    views = int(number * multiplier)
    if not 0 <= views <= _MAX_TELEGRAM_VIEWS:
        raise ValueError("Счётчик Telegram вышел за допустимый диапазон")
    return views


async def _read_limited_html(response: aiohttp.ClientResponse) -> str:
    content_length = response.content_length
    if content_length is not None and content_length > _MAX_PUBLIC_HTML_BYTES:
        raise ValueError("Ответ Telegram превышает допустимый размер")
    payload = bytearray()
    async for chunk in response.content.iter_chunked(16 * 1024):
        payload.extend(chunk)
        if len(payload) > _MAX_PUBLIC_HTML_BYTES:
            raise ValueError("Ответ Telegram превышает допустимый размер")
    return payload.decode(response.charset or "utf-8", errors="replace")


async def _fetch_public_views(
    session: aiohttp.ClientSession,
    channel_username: str,
    message_id: int,
) -> int:
    username = channel_username.lstrip("@")
    if not _PUBLIC_USERNAME_RE.fullmatch(username) or message_id <= 0:
        raise ValueError("Некорректная публичная ссылка Telegram")
    url = f"https://t.me/{username}/{message_id}?embed=1&mode=tme"
    for attempt in range(2):
        try:
            async with session.get(url, allow_redirects=False) as response:
                if response.status == 200:
                    content_type = response.headers.get("Content-Type", "")
                    if "text/html" not in content_type.lower():
                        raise ValueError("Telegram вернул неожиданный тип ответа")
                    return parse_public_views_html(await _read_limited_html(response))
                if response.status == 429 or response.status >= 500:
                    if attempt == 0:
                        retry_after = response.headers.get("Retry-After", "")
                        delay = min(float(retry_after), 5.0) if retry_after.isdigit() else 1.0
                        await asyncio.sleep(delay + random.uniform(0, 0.25))
                        continue
                raise RuntimeError(f"Telegram public page returned HTTP {response.status}")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt == 0:
                await asyncio.sleep(1.0 + random.uniform(0, 0.25))
                continue
            raise
    raise RuntimeError("Telegram public page is unavailable")


class ChannelMetricsService:
    """Обновляет views через MTProto или read-only страницу публичного поста."""

    @staticmethod
    async def refresh_shop(shop_id: int, *, limit: int = 100) -> int:
        if not ChannelAttributionService.enabled_for_shop(shop_id):
            raise ValueError("Аналитика публикаций не включена для магазина")

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

        if (
            settings.telegram_api_id
            and settings.telegram_api_hash
            and settings.telegram_session
        ):
            return await ChannelMetricsService._refresh_mtproto(connection, posts)
        if settings.channel_public_metrics_enabled and connection.channel_username:
            return await ChannelMetricsService._refresh_public(connection, posts)
        raise RuntimeError(
            "Просмотры недоступны: настройте MTProto или включите public fallback "
            "для канала с username"
        )

    @staticmethod
    async def _refresh_mtproto(
        connection: ChannelConnection, posts: list[ChannelPost]
    ) -> int:
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
                "Channel metrics refreshed source=mtproto shop=%d posts=%d",
                connection.shop_id,
                len(posts),
            )
            return len(posts)
        finally:
            await client.disconnect()

    @staticmethod
    async def _refresh_public(connection: ChannelConnection, posts: list[ChannelPost]) -> int:
        timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_read=7)
        semaphore = asyncio.Semaphore(4)
        headers = {"User-Agent": "TGShop-PublicMetrics/1.0"}

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as http:
            async def fetch(post: ChannelPost) -> tuple[int, int] | None:
                async with semaphore:
                    try:
                        views = await _fetch_public_views(
                            http,
                            connection.channel_username or "",
                            post.telegram_message_id,
                        )
                        return post.id, views
                    except Exception as exc:
                        logger.warning(
                            "Public Telegram metric failed shop=%d post=%d error=%s",
                            connection.shop_id,
                            post.id,
                            type(exc).__name__,
                        )
                        return None

            tasks = [asyncio.create_task(fetch(post)) for post in posts]
            done, pending = await asyncio.wait(
                tasks, timeout=_PUBLIC_REFRESH_DEADLINE_SECONDS
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
                logger.warning(
                    "Public Telegram metrics deadline reached shop=%d pending=%d",
                    connection.shop_id,
                    len(pending),
                )
            results = [task.result() for task in done]

        metrics = {result[0]: result[1] for result in results if result is not None}
        if not metrics:
            raise RuntimeError("Telegram public metrics are temporarily unavailable")

        now = datetime.now()
        async with async_session() as session:
            current_posts = (
                await session.execute(select(ChannelPost).where(ChannelPost.id.in_(metrics)))
            ).scalars().all()
            for post in current_posts:
                post.telegram_views = max(post.telegram_views or 0, metrics[post.id])
                post.metrics_updated_at = now
            await session.commit()

        logger.info(
            "Channel metrics refreshed source=public shop=%d posts=%d failed=%d",
            connection.shop_id,
            len(metrics),
            len(posts) - len(metrics),
        )
        return len(metrics)

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
