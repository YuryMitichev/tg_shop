from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from sqlalchemy import or_, select, update

from app.core.config import settings
from app.database.db import async_session
from app.models.channel_import import (
    ChannelPost,
    ChannelPostButtonJob,
    ProductSourceRef,
)
from app.models.product import Product


OPEN_JOB_STATUSES = {"queued", "retry_wait", "needs_action"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def product_start_param(shop_id: int, product_id: int) -> str:
    return f"shop_{shop_id}_product_{product_id}"


def product_deep_link(bot_username: str, shop_id: int, product_id: int) -> str:
    username = bot_username.lstrip("@")
    return f"https://t.me/{username}?startapp={product_start_param(shop_id, product_id)}"


def is_managed_product_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        values = parse_qs(urlparse(url).query).get("startapp", [])
    except ValueError:
        return False
    return any(
        value.startswith("shop_") and "_product_" in value
        for value in values
    )


def strip_managed_product_buttons(markup: dict | None) -> dict | None:
    """Оставляет исходные кнопки поста, удаляя только управляемые нами URL."""
    if not markup or not isinstance(markup.get("inline_keyboard"), list):
        return None
    result = deepcopy(markup)
    rows: list[list[dict]] = []
    for row in result.get("inline_keyboard", []):
        if not isinstance(row, list):
            continue
        cleaned = [
            button
            for button in row
            if isinstance(button, dict) and not is_managed_product_url(button.get("url"))
        ]
        if cleaned:
            rows.append(cleaned)
    return {"inline_keyboard": rows} if rows else None


class ChannelPostButtonService:
    @staticmethod
    def enabled_for_shop(shop_id: int) -> bool:
        return settings.channel_product_buttons_enabled and (
            settings.channel_product_buttons_pilot_shop_id is None
            or settings.channel_product_buttons_pilot_shop_id == shop_id
        )

    @staticmethod
    def capture_source_markup(post: ChannelPost, raw_data: dict | None) -> None:
        if not raw_data or not raw_data.get("reply_markup_known"):
            return
        post.source_reply_markup = strip_managed_product_buttons(raw_data.get("reply_markup"))
        post.source_reply_markup_known = True

    @staticmethod
    async def enqueue_in_session(
        session,
        post: ChannelPost,
        *,
        reason: str,
        force: bool = False,
    ) -> ChannelPostButtonJob | None:
        if not force and not ChannelPostButtonService.enabled_for_shop(post.shop_id):
            return None

        post.button_version += 1
        await session.execute(
            update(ChannelPostButtonJob)
            .where(
                ChannelPostButtonJob.post_id == post.id,
                ChannelPostButtonJob.status.in_(OPEN_JOB_STATUSES),
            )
            .values(status="superseded", locked_by=None, locked_until=None)
        )
        job = ChannelPostButtonJob(
            shop_id=post.shop_id,
            post_id=post.id,
            button_version=post.button_version,
            status="queued",
            reason=reason,
            available_at=_utcnow(),
        )
        session.add(job)
        return job

    @staticmethod
    async def list_links(shop_id: int, post_id: int) -> dict:
        async with async_session() as session:
            post = (
                await session.execute(
                    select(ChannelPost).where(
                        ChannelPost.id == post_id,
                        ChannelPost.shop_id == shop_id,
                    )
                )
            ).scalar_one_or_none()
            if post is None:
                raise ValueError("Публикация не найдена")

            rows = (
                await session.execute(
                    select(ProductSourceRef, Product)
                    .join(Product, Product.id == ProductSourceRef.product_id)
                    .where(
                        ProductSourceRef.shop_id == shop_id,
                        ProductSourceRef.connection_id == post.connection_id,
                        ProductSourceRef.telegram_message_id == post.telegram_message_id,
                    )
                    .order_by(ProductSourceRef.candidate_position, ProductSourceRef.id)
                )
            ).all()
            latest_job = (
                await session.execute(
                    select(ChannelPostButtonJob)
                    .where(ChannelPostButtonJob.post_id == post.id)
                    .order_by(ChannelPostButtonJob.button_version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            return {
                "post_id": post.id,
                "button_version": post.button_version,
                "source_reply_markup_known": post.source_reply_markup_known,
                "links": [
                    {
                        "id": ref.id,
                        "product_id": product.id,
                        "product_name": product.name,
                        "is_active": product.is_active,
                        "position": ref.candidate_position,
                        "source_kind": ref.source_kind,
                        "sku": ref.sku,
                    }
                    for ref, product in rows
                ],
                "sync": ChannelPostButtonService._job_dict(latest_job),
            }

    @staticmethod
    def _job_dict(job: ChannelPostButtonJob | None) -> dict | None:
        if job is None:
            return None
        return {
            "id": job.id,
            "status": job.status,
            "attempts": job.attempts,
            "error_code": job.error_code,
            "last_error": job.last_error,
            "button_version": job.button_version,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }

    @staticmethod
    async def add_link(shop_id: int, post_id: int, product_id: int) -> dict:
        ChannelPostButtonService._require_enabled(shop_id)
        async with async_session() as session:
            post = await ChannelPostButtonService._locked_post(session, shop_id, post_id)
            product = await ChannelPostButtonService._active_product(session, shop_id, product_id)
            existing = await ChannelPostButtonService._refs_for_post(session, post)
            if any(ref.product_id == product.id for ref in existing):
                raise ValueError("Этот товар уже прикреплён к публикации")
            # AI использует позиции 0..N. Ручные слоты держим в отдельном диапазоне,
            # чтобы добавление ссылки не заняло место ещё не подтверждённого кандидата.
            next_position = max(
                (ref.candidate_position for ref in existing if ref.candidate_position >= 1_000_000),
                default=999_999,
            ) + 1
            session.add(
                ProductSourceRef(
                    shop_id=shop_id,
                    product_id=product.id,
                    connection_id=post.connection_id,
                    telegram_message_id=post.telegram_message_id,
                    candidate_position=next_position,
                    source_kind="manual",
                )
            )
            await ChannelPostButtonService.enqueue_in_session(
                session, post, reason="manual_link_added"
            )
            await session.commit()
        return await ChannelPostButtonService.list_links(shop_id, post_id)

    @staticmethod
    async def replace_link(shop_id: int, post_id: int, link_id: int, product_id: int) -> dict:
        ChannelPostButtonService._require_enabled(shop_id)
        async with async_session() as session:
            post = await ChannelPostButtonService._locked_post(session, shop_id, post_id)
            product = await ChannelPostButtonService._active_product(session, shop_id, product_id)
            refs = await ChannelPostButtonService._refs_for_post(session, post)
            ref = next((item for item in refs if item.id == link_id), None)
            if ref is None:
                raise ValueError("Привязка не найдена")
            if any(item.id != ref.id and item.product_id == product.id for item in refs):
                raise ValueError("Этот товар уже прикреплён к публикации")
            ref.product_id = product.id
            ref.source_kind = "manual"
            ref.sku = None
            ref.fingerprint = None
            await ChannelPostButtonService.enqueue_in_session(
                session, post, reason="manual_link_replaced"
            )
            await session.commit()
        return await ChannelPostButtonService.list_links(shop_id, post_id)

    @staticmethod
    async def remove_link(shop_id: int, post_id: int, link_id: int) -> dict:
        ChannelPostButtonService._require_enabled(shop_id)
        async with async_session() as session:
            post = await ChannelPostButtonService._locked_post(session, shop_id, post_id)
            refs = await ChannelPostButtonService._refs_for_post(session, post)
            ref = next((item for item in refs if item.id == link_id), None)
            if ref is None:
                raise ValueError("Привязка не найдена")
            await session.delete(ref)
            await ChannelPostButtonService.enqueue_in_session(
                session, post, reason="manual_link_removed"
            )
            await session.commit()
        return await ChannelPostButtonService.list_links(shop_id, post_id)

    @staticmethod
    async def retry_post(
        shop_id: int,
        post_id: int,
        *,
        allow_replace_unknown: bool = False,
    ) -> dict:
        ChannelPostButtonService._require_enabled(shop_id)
        async with async_session() as session:
            post = await ChannelPostButtonService._locked_post(session, shop_id, post_id)
            if not post.source_reply_markup_known:
                if not allow_replace_unknown:
                    raise ValueError(
                        "Неизвестно, были ли у старого поста свои кнопки. "
                        "Подтвердите их замену вручную."
                    )
                post.source_reply_markup = None
                post.source_reply_markup_known = True
            await ChannelPostButtonService.enqueue_in_session(
                session, post, reason="manual_retry", force=True
            )
            await session.commit()
        return await ChannelPostButtonService.list_links(shop_id, post_id)

    @staticmethod
    async def enqueue_product_change_in_session(
        session,
        shop_id: int,
        product_id: int,
        *,
        reason: str,
    ) -> None:
        if not ChannelPostButtonService.enabled_for_shop(shop_id):
            return
        posts = (
            await session.execute(
                select(ChannelPost)
                .join(
                    ProductSourceRef,
                    (ProductSourceRef.connection_id == ChannelPost.connection_id)
                    & (ProductSourceRef.telegram_message_id == ChannelPost.telegram_message_id),
                )
                .where(
                    ChannelPost.shop_id == shop_id,
                    ProductSourceRef.product_id == product_id,
                )
                .with_for_update()
            )
        ).scalars().all()
        seen: set[int] = set()
        for post in posts:
            if post.id in seen:
                continue
            seen.add(post.id)
            await ChannelPostButtonService.enqueue_in_session(session, post, reason=reason)

    @staticmethod
    async def search_products(shop_id: int, query: str, limit: int = 8) -> list[dict]:
        normalized = query.strip()
        if not normalized:
            return []
        conditions = [
            Product.name.ilike(f"%{normalized}%"),
            select(ProductSourceRef.id)
            .where(
                ProductSourceRef.shop_id == shop_id,
                ProductSourceRef.product_id == Product.id,
                ProductSourceRef.sku.ilike(f"%{normalized}%"),
            )
            .exists(),
        ]
        if normalized.isdigit():
            conditions.append(Product.id == int(normalized))
        async with async_session() as session:
            products = (
                await session.execute(
                    select(Product)
                    .where(
                        Product.shop_id == shop_id,
                        Product.is_active.is_(True),
                        or_(*conditions),
                    )
                    .order_by(Product.name, Product.id)
                    .limit(limit)
                )
            ).scalars().all()
            return [{"id": item.id, "name": item.name} for item in products]

    @staticmethod
    async def _locked_post(session, shop_id: int, post_id: int) -> ChannelPost:
        post = (
            await session.execute(
                select(ChannelPost)
                .where(ChannelPost.id == post_id, ChannelPost.shop_id == shop_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if post is None:
            raise ValueError("Публикация не найдена")
        return post

    @staticmethod
    def _require_enabled(shop_id: int) -> None:
        if not ChannelPostButtonService.enabled_for_shop(shop_id):
            raise ValueError("Кнопки товаров пока не включены для этого магазина")

    @staticmethod
    async def _active_product(session, shop_id: int, product_id: int) -> Product:
        product = (
            await session.execute(
                select(Product).where(
                    Product.id == product_id,
                    Product.shop_id == shop_id,
                    Product.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if product is None:
            raise ValueError("Активный товар этого магазина не найден")
        return product

    @staticmethod
    async def _refs_for_post(session, post: ChannelPost) -> list[ProductSourceRef]:
        return list(
            (
                await session.execute(
                    select(ProductSourceRef)
                    .where(
                        ProductSourceRef.shop_id == post.shop_id,
                        ProductSourceRef.connection_id == post.connection_id,
                        ProductSourceRef.telegram_message_id == post.telegram_message_id,
                    )
                    .order_by(ProductSourceRef.candidate_position, ProductSourceRef.id)
                    .with_for_update()
                )
            ).scalars().all()
        )
