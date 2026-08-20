from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.database.db import async_session
from app.models.category import Category
from app.models.channel_import import (
    CatalogAnalysisRun,
    CatalogImportCandidate,
    CatalogImportJob,
    ChannelConnection,
    ChannelPost,
    ChannelPostButtonJob,
    ChannelPostMedia,
    PrefilterFeedback,
    ProductSourceRef,
)
from app.models.product import Product
from app.models.product_attribute_def import ProductAttributeDef
from app.models.product_photo import ProductPhoto
from app.models.product_variant import ProductVariant
from app.services.product_attr_service import _slugify


EDITABLE_STATUSES = {"pending", "needs_manual", "possible_duplicate"}
TERMINAL_CANDIDATE_STATUSES = {"approved", "rejected", "duplicate_skipped"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_text(value: str | None) -> str:
    return re.sub(r"[^a-zа-яё0-9]+", " ", (value or "").casefold()).strip()


def product_fingerprint(name: str | None, sku: str | None, variants: list[dict]) -> str:
    prices = sorted(str(v.get("price")) for v in variants if v.get("price") is not None)
    source = "|".join([normalize_text(name), normalize_text(sku), ",".join(prices)])
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


class ChannelImportService:
    @staticmethod
    def mtproto_configured() -> bool:
        return bool(
            settings.telegram_api_id
            and settings.telegram_api_hash
            and settings.telegram_session
        )

    @staticmethod
    def enabled_for_shop(shop_id: int) -> bool:
        return settings.channel_import_enabled and (
            settings.channel_import_pilot_shop_id is None
            or settings.channel_import_pilot_shop_id == shop_id
        )

    @staticmethod
    async def get_connection(shop_id: int) -> ChannelConnection | None:
        async with async_session() as session:
            return (
                await session.execute(
                    select(ChannelConnection).where(ChannelConnection.shop_id == shop_id)
                )
            ).scalar_one_or_none()

    @staticmethod
    async def connect_channel(
        shop_id: int,
        *,
        channel_id: int,
        channel_title: str,
        channel_username: str | None,
        connected_by: int,
    ) -> ChannelConnection:
        async with async_session() as session:
            existing_channel = (
                await session.execute(
                    select(ChannelConnection).where(
                        ChannelConnection.channel_id == channel_id,
                        ChannelConnection.shop_id != shop_id,
                    )
                )
            ).scalar_one_or_none()
            if existing_channel:
                raise ValueError("Этот канал уже подключён к другому магазину")

            connection = (
                await session.execute(
                    select(ChannelConnection).where(ChannelConnection.shop_id == shop_id)
                )
            ).scalar_one_or_none()
            if connection is None:
                connection = ChannelConnection(
                    shop_id=shop_id,
                    channel_id=channel_id,
                    channel_title=channel_title,
                    channel_username=channel_username,
                    connected_by=connected_by,
                    backfill_status=(
                        "pending" if ChannelImportService.mtproto_configured()
                        else "not_configured"
                    ),
                )
                session.add(connection)
            else:
                channel_changed = connection.channel_id != channel_id
                connection.channel_id = channel_id
                connection.channel_title = channel_title
                connection.channel_username = channel_username
                connection.connected_by = connected_by
                connection.is_active = True
                connection.backfill_status = (
                    "pending" if ChannelImportService.mtproto_configured()
                    else "not_configured"
                )
                connection.backfill_error = None
                if channel_changed:
                    connection.storefront_message_id = None
                    connection.storefront_status = "not_created"
                    connection.storefront_error_code = None
                    connection.storefront_error = None
                    connection.storefront_updated_at = None
            await session.commit()
            await session.refresh(connection)
            return connection

    @staticmethod
    async def update_settings(
        shop_id: int, *, is_paused: bool | None = None, notifications_enabled: bool | None = None
    ) -> ChannelConnection:
        async with async_session() as session:
            connection = (
                await session.execute(
                    select(ChannelConnection).where(ChannelConnection.shop_id == shop_id)
                )
            ).scalar_one_or_none()
            if connection is None:
                raise ValueError("Канал ещё не подключён")
            if is_paused is not None:
                connection.is_paused = is_paused
            if notifications_enabled is not None:
                connection.notifications_enabled = notifications_enabled
            await session.commit()
            await session.refresh(connection)
            return connection

    @staticmethod
    async def ingest_post(
        shop_id: int,
        *,
        telegram_message_id: int,
        text: str | None,
        media: list[dict] | None = None,
        media_group_id: str | None = None,
        published_at: datetime | None = None,
        edited_at: datetime | None = None,
        raw_data: dict | None = None,
    ) -> int | None:
        """Upsert поста и постановка его версии в очередь.

        Подтверждённый товар не меняется: правка только фиксируется в журнале.
        Для неподтверждённого черновика старая версия помечается superseded.
        """
        from app.services.channel_post_button_service import ChannelPostButtonService

        async with async_session() as session:
            connection = (
                await session.execute(
                    select(ChannelConnection).where(
                        ChannelConnection.shop_id == shop_id,
                        ChannelConnection.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if connection is None or connection.is_paused:
                return None

            post = (
                await session.execute(
                    select(ChannelPost).where(
                        ChannelPost.connection_id == connection.id,
                        ChannelPost.telegram_message_id == telegram_message_id,
                    )
                )
            ).scalar_one_or_none()
            if post is None and media_group_id:
                post = (
                    await session.execute(
                        select(ChannelPost).where(
                            ChannelPost.connection_id == connection.id,
                            ChannelPost.media_group_id == media_group_id,
                        ).order_by(ChannelPost.id).limit(1)
                    )
                ).scalar_one_or_none()
            is_edit = post is not None
            if post is None:
                post = ChannelPost(
                    shop_id=shop_id,
                    connection_id=connection.id,
                    telegram_message_id=telegram_message_id,
                    version=1,
                )
                session.add(post)
                await session.flush()
            else:
                if edited_at is None and post.text == text:
                    existing_job = (
                        await session.execute(
                            select(CatalogImportJob.id).where(
                                CatalogImportJob.post_id == post.id,
                                CatalogImportJob.post_version == post.version,
                            )
                        )
                    ).scalar_one_or_none()
                    return existing_job
                already_published = (
                    await session.execute(
                        select(ProductSourceRef.id).where(
                            ProductSourceRef.connection_id == connection.id,
                            ProductSourceRef.telegram_message_id == telegram_message_id,
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                if already_published:
                    post.version += 1
                    post.text = text
                    post.edited_at = edited_at or _utcnow()
                    post.status = "published_unchanged"
                    post.raw_data = raw_data
                    ChannelPostButtonService.capture_source_markup(post, raw_data)
                    await ChannelPostButtonService.enqueue_in_session(
                        session, post, reason="source_post_edited"
                    )
                    await session.commit()
                    return None
                post.version += 1
                old_candidates = (
                    await session.execute(
                        select(CatalogImportCandidate)
                        .join(CatalogImportJob, CatalogImportCandidate.job_id == CatalogImportJob.id)
                        .where(
                            CatalogImportJob.post_id == post.id,
                            CatalogImportCandidate.status.in_(EDITABLE_STATUSES),
                        )
                    )
                ).scalars().all()
                for candidate in old_candidates:
                    candidate.status = "superseded"

            post.text = text
            post.media_group_id = media_group_id
            post.published_at = published_at or post.published_at or _utcnow()
            post.edited_at = edited_at if is_edit else None
            post.status = "received"
            post.raw_data = raw_data
            ChannelPostButtonService.capture_source_markup(post, raw_data)

            if media is not None:
                old_media = (
                    await session.execute(
                        select(ChannelPostMedia).where(ChannelPostMedia.post_id == post.id)
                    )
                ).scalars().all()
                for item in old_media:
                    await session.delete(item)
                for position, item in enumerate(media):
                    session.add(
                        ChannelPostMedia(
                            post_id=post.id,
                            file_id=item["file_id"],
                            file_unique_id=item.get("file_unique_id"),
                            media_type=item.get("media_type", "photo"),
                            position=position,
                        )
                    )

            job = CatalogImportJob(
                shop_id=shop_id,
                post_id=post.id,
                post_version=post.version,
                status="queued",
                available_at=_utcnow(),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job.id

    @staticmethod
    async def enqueue_backfill(shop_id: int) -> int:
        if not ChannelImportService.mtproto_configured():
            raise ValueError("Исторический импорт не настроен; realtime продолжает работать")
        connection = await ChannelImportService.get_connection(shop_id)
        if connection is None:
            raise ValueError("Канал ещё не подключён")
        from app.services.channel_backfill_service import ChannelBackfillService

        return await ChannelBackfillService.backfill(connection.id, limit=50)

    @staticmethod
    async def get_catalog_context(shop_id: int) -> tuple[list[str], list[str]]:
        async with async_session() as session:
            categories = (
                await session.execute(
                    select(Category.name).where(Category.shop_id == shop_id).order_by(Category.name)
                )
            ).scalars().all()
            attrs = (
                await session.execute(
                    select(ProductAttributeDef.label)
                    .where(ProductAttributeDef.shop_id == shop_id)
                    .order_by(ProductAttributeDef.position)
                )
            ).scalars().all()
            return list(categories), list(attrs)

    @staticmethod
    async def find_duplicates(shop_id: int, product: dict) -> list[dict]:
        sku = (product.get("sku") or "").casefold().strip()
        if sku:
            async with async_session() as session:
                ref = (
                    await session.execute(
                        select(ProductSourceRef).where(
                            ProductSourceRef.shop_id == shop_id,
                            func.lower(ProductSourceRef.sku) == sku,
                        )
                    )
                ).scalar_one_or_none()
                if ref:
                    return [{"product_id": ref.product_id, "score": 1.0, "reason": "sku"}]

        async with async_session() as session:
            base_query = (
                select(Product)
                .options(selectinload(Product.category), selectinload(Product.variants))
                .where(Product.shop_id == shop_id)
            )
            dialect = session.get_bind().dialect.name
            if dialect == "postgresql" and product.get("name"):
                trigram = func.similarity(Product.name, product["name"])
                rows = (
                    await session.execute(
                        select(Product, trigram.label("trigram_score"))
                        .options(selectinload(Product.category), selectinload(Product.variants))
                        .where(Product.shop_id == shop_id, trigram >= 0.25)
                        .order_by(trigram.desc())
                        .limit(20)
                    )
                ).all()
                products_with_trigram = [(row[0], float(row[1])) for row in rows]
            else:
                products = (await session.execute(base_query)).scalars().all()
                products_with_trigram = [(product_row, None) for product_row in products]

        target_name = normalize_text(product.get("name"))
        target_category = normalize_text(product.get("category_name"))
        target_prices = {
            int(v["price"]) for v in product.get("variants", []) if v.get("price") is not None
        }
        matches: list[dict] = []
        for existing, trigram_score in products_with_trigram:
            existing_name = normalize_text(existing.name)
            if not target_name or not existing_name:
                continue
            sequence = SequenceMatcher(None, target_name, existing_name).ratio()
            target_tokens, existing_tokens = set(target_name.split()), set(existing_name.split())
            union = target_tokens | existing_tokens
            token_score = len(target_tokens & existing_tokens) / len(union) if union else 0
            lexical_score = sequence * 0.7 + token_score * 0.3
            score = max(lexical_score, trigram_score or 0.0)
            if target_category and existing.category:
                score += 0.04 if target_category == normalize_text(existing.category.name) else -0.05
            existing_prices = {variant.price for variant in existing.variants}
            if target_prices and existing_prices:
                score += 0.04 if target_prices & existing_prices else -0.03
            score = max(0.0, min(1.0, score))
            if score >= 0.55:
                matches.append(
                    {
                        "product_id": existing.id,
                        "name": existing.name,
                        "category": existing.category.name if existing.category else None,
                        "prices": sorted(existing_prices),
                        "score": round(score, 4),
                        "reason": "name_category_price",
                    }
                )
        return sorted(matches, key=lambda item: item["score"], reverse=True)[:5]

    @staticmethod
    async def list_candidates(shop_id: int, *, status: str | None = None) -> list[dict]:
        async with async_session() as session:
            query = (
                select(CatalogImportCandidate, CatalogImportJob, ChannelPost)
                .join(CatalogImportJob, CatalogImportCandidate.job_id == CatalogImportJob.id)
                .join(ChannelPost, CatalogImportJob.post_id == ChannelPost.id)
                .where(CatalogImportCandidate.shop_id == shop_id)
                .order_by(CatalogImportCandidate.created_at.desc())
            )
            if status:
                query = query.where(CatalogImportCandidate.status == status)
            rows = (await session.execute(query)).all()
            return [ChannelImportService._candidate_dict(*row) for row in rows]

    @staticmethod
    async def get_candidate(shop_id: int, candidate_id: int) -> dict | None:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(CatalogImportCandidate, CatalogImportJob, ChannelPost)
                    .join(CatalogImportJob, CatalogImportCandidate.job_id == CatalogImportJob.id)
                    .join(ChannelPost, CatalogImportJob.post_id == ChannelPost.id)
                    .where(
                        CatalogImportCandidate.shop_id == shop_id,
                        CatalogImportCandidate.id == candidate_id,
                    )
                )
            ).one_or_none()
            if row is None:
                return None
            candidate, job, post = row
            media = (
                await session.execute(
                    select(ChannelPostMedia)
                    .where(ChannelPostMedia.post_id == post.id)
                    .order_by(ChannelPostMedia.position)
                )
            ).scalars().all()
            result = ChannelImportService._candidate_dict(candidate, job, post)
            result["photos"] = [
                {"id": item.id, "file_id": item.file_id, "position": item.position} for item in media
            ]
            return result

    @staticmethod
    def _candidate_dict(candidate, job, post) -> dict:
        return {
            "id": candidate.id,
            "status": candidate.status,
            "name": candidate.name,
            "description": candidate.description,
            "category_name": candidate.category_name,
            "proposed_category": candidate.proposed_category,
            "sku": candidate.sku,
            "currency": candidate.currency,
            "variants": candidate.variants or [],
            "attributes": candidate.attributes or {},
            "field_confidence": candidate.field_confidence or {},
            "duplicate_product_id": candidate.duplicate_product_id,
            "duplicate_score": candidate.duplicate_score,
            "product_id": candidate.product_id,
            "owner_note": candidate.owner_note,
            "post": {
                "id": post.id,
                "telegram_message_id": post.telegram_message_id,
                "version": post.version,
                "text": post.text,
                "published_at": post.published_at.isoformat() if post.published_at else None,
            },
            "job_id": job.id,
            "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        }

    @staticmethod
    async def update_candidate(shop_id: int, candidate_id: int, values: dict) -> dict:
        allowed = {
            "name", "description", "category_name", "proposed_category", "sku",
            "currency", "variants", "attributes", "owner_note",
        }
        async with async_session() as session:
            candidate = (
                await session.execute(
                    select(CatalogImportCandidate).where(
                        CatalogImportCandidate.id == candidate_id,
                        CatalogImportCandidate.shop_id == shop_id,
                    )
                )
            ).scalar_one_or_none()
            if candidate is None:
                raise ValueError("Черновик не найден")
            if candidate.status not in EDITABLE_STATUSES:
                raise ValueError("Этот черновик уже закрыт")
            for key, value in values.items():
                if key in allowed:
                    setattr(candidate, key, value)
            candidate.fingerprint = product_fingerprint(
                candidate.name, candidate.sku, candidate.variants or []
            )
            await session.commit()
        result = await ChannelImportService.get_candidate(shop_id, candidate_id)
        assert result is not None
        return result

    @staticmethod
    async def approve_candidate(shop_id: int, candidate_id: int) -> int:
        """Публикует черновик одной транзакцией вместе со справочниками."""
        async with async_session() as session:
            row = (
                await session.execute(
                    select(CatalogImportCandidate, CatalogImportJob, ChannelPost)
                    .join(CatalogImportJob, CatalogImportCandidate.job_id == CatalogImportJob.id)
                    .join(ChannelPost, CatalogImportJob.post_id == ChannelPost.id)
                    .where(
                        CatalogImportCandidate.id == candidate_id,
                        CatalogImportCandidate.shop_id == shop_id,
                    )
                    .with_for_update()
                )
            ).one_or_none()
            if row is None:
                raise ValueError("Черновик не найден")
            candidate, job, post = row
            if candidate.status == "approved" and candidate.product_id:
                return candidate.product_id
            if candidate.status not in EDITABLE_STATUSES:
                raise ValueError("Черновик уже закрыт")
            if not candidate.name or not candidate.category_name:
                raise ValueError("Для подтверждения нужны название и категория")
            if (candidate.currency or "RUB").upper() not in {"RUB", "RUR", "₽"}:
                raise ValueError("Перед публикацией исправьте валюту на RUB")
            variants = candidate.variants or []
            if not variants:
                raise ValueError("Добавьте хотя бы один вариант товара")
            for variant in variants:
                if not isinstance(variant.get("price"), int) or variant["price"] < 0:
                    raise ValueError("Цена должна быть целым числом рублей")
                if variant.get("stock") is None:
                    raise ValueError("Укажите остаток для каждого варианта")
                variant_currency = str(variant.get("currency") or candidate.currency or "RUB").upper()
                if variant_currency not in {"RUB", "RUR", "₽"}:
                    raise ValueError("Перед публикацией исправьте валюту всех вариантов на RUB")

            source_exists = (
                await session.execute(
                    select(ProductSourceRef).where(
                        ProductSourceRef.connection_id == post.connection_id,
                        ProductSourceRef.telegram_message_id == post.telegram_message_id,
                        ProductSourceRef.candidate_position == candidate.position,
                    )
                )
            ).scalar_one_or_none()
            if source_exists:
                candidate.status = "approved"
                candidate.product_id = source_exists.product_id
                post.status = "published"
                from app.services.channel_post_button_service import ChannelPostButtonService

                await ChannelPostButtonService.enqueue_in_session(
                    session, post, reason="candidate_approved_existing_source"
                )
                await session.commit()
                return source_exists.product_id

            category = (
                await session.execute(
                    select(Category).where(
                        Category.shop_id == shop_id,
                        func.lower(Category.name) == candidate.category_name.casefold(),
                    )
                )
            ).scalar_one_or_none()
            if category is None:
                category = Category(shop_id=shop_id, name=candidate.category_name.strip())
                session.add(category)
                await session.flush()

            attr_values = dict(candidate.attributes or {})
            for variant in variants:
                attr_values.update(variant.get("attributes") or {})
            existing_defs = (
                await session.execute(
                    select(ProductAttributeDef).where(ProductAttributeDef.shop_id == shop_id)
                )
            ).scalars().all()
            defs_by_label = {normalize_text(item.label): item for item in existing_defs}
            defs_by_key = {item.key: item for item in existing_defs}
            next_position = max((item.position for item in existing_defs), default=-1) + 1
            attribute_key_map: dict[str, str] = {}
            for label in attr_values:
                normalized = normalize_text(label)
                definition = defs_by_label.get(normalized)
                if definition is None:
                    key = _slugify(label)
                    suffix = 2
                    base_key = key
                    while key in defs_by_key:
                        key = f"{base_key}_{suffix}"
                        suffix += 1
                    definition = ProductAttributeDef(
                        shop_id=shop_id,
                        key=key,
                        label=label.strip(),
                        position=next_position,
                    )
                    next_position += 1
                    session.add(definition)
                    defs_by_key[key] = definition
                    defs_by_label[normalized] = definition
                attribute_key_map[label] = definition.key

            product = Product(
                shop_id=shop_id,
                category_id=category.id,
                name=candidate.name.strip(),
                description=(candidate.description or "").strip(),
                is_active=True,
            )
            for variant in variants:
                merged = dict(candidate.attributes or {})
                merged.update(variant.get("attributes") or {})
                mapped_attrs = {attribute_key_map[label]: str(value) for label, value in merged.items()}
                product.variants.append(
                    ProductVariant(
                        shop_id=shop_id,
                        volume=(variant.get("title") or variant.get("volume") or "—").strip(),
                        price=variant["price"],
                        stock=max(0, int(variant["stock"])),
                        attributes=mapped_attrs,
                    )
                )
            media = (
                await session.execute(
                    select(ChannelPostMedia)
                    .where(ChannelPostMedia.post_id == post.id)
                    .order_by(ChannelPostMedia.position)
                )
            ).scalars().all()
            for item in media:
                product.photos.append(
                    ProductPhoto(shop_id=shop_id, file_id=item.file_id, position=item.position)
                )
            session.add(product)
            await session.flush()

            session.add(
                ProductSourceRef(
                    shop_id=shop_id,
                    product_id=product.id,
                    connection_id=post.connection_id,
                    telegram_message_id=post.telegram_message_id,
                    candidate_position=candidate.position,
                    sku=candidate.sku,
                    fingerprint=candidate.fingerprint,
                    source_kind="ai",
                )
            )
            candidate.product_id = product.id
            candidate.status = "approved"
            post.status = "published"
            from app.services.channel_post_button_service import ChannelPostButtonService

            await ChannelPostButtonService.enqueue_in_session(
                session, post, reason="candidate_approved"
            )
            await session.commit()
            return product.id

    @staticmethod
    async def set_candidate_status(
        shop_id: int, candidate_id: int, status: str, owner_label: str
    ) -> None:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(CatalogImportCandidate, CatalogImportJob)
                    .join(CatalogImportJob, CatalogImportCandidate.job_id == CatalogImportJob.id)
                    .where(
                        CatalogImportCandidate.id == candidate_id,
                        CatalogImportCandidate.shop_id == shop_id,
                    )
                )
            ).one_or_none()
            if row is None:
                raise ValueError("Черновик не найден")
            candidate, job = row
            if candidate.status in TERMINAL_CANDIDATE_STATUSES:
                return
            candidate.status = status
            feedback = (
                await session.execute(
                    select(PrefilterFeedback).where(PrefilterFeedback.post_id == job.post_id)
                )
            ).scalar_one_or_none()
            if feedback:
                feedback.owner_label = owner_label
            await session.commit()

    @staticmethod
    async def retry_job(shop_id: int, job_id: int) -> None:
        async with async_session() as session:
            job = (
                await session.execute(
                    select(CatalogImportJob).where(
                        CatalogImportJob.id == job_id,
                        CatalogImportJob.shop_id == shop_id,
                    )
                )
            ).scalar_one_or_none()
            if job is None:
                raise ValueError("Задание не найдено")
            job.status = "queued"
            job.attempts = 0
            job.available_at = _utcnow()
            job.locked_by = None
            job.locked_until = None
            job.last_error = None
            await session.commit()

    @staticmethod
    async def reanalyze_candidate(shop_id: int, candidate_id: int) -> int:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(CatalogImportCandidate, CatalogImportJob, ChannelPost)
                    .join(CatalogImportJob, CatalogImportCandidate.job_id == CatalogImportJob.id)
                    .join(ChannelPost, CatalogImportJob.post_id == ChannelPost.id)
                    .where(
                        CatalogImportCandidate.id == candidate_id,
                        CatalogImportCandidate.shop_id == shop_id,
                    )
                    .with_for_update()
                )
            ).one_or_none()
            if row is None:
                raise ValueError("Черновик не найден")
            candidate, old_job, post = row
            if candidate.status == "approved":
                raise ValueError("Опубликованный товар автоматически не переанализируется")
            candidates = (
                await session.execute(
                    select(CatalogImportCandidate)
                    .join(CatalogImportJob, CatalogImportCandidate.job_id == CatalogImportJob.id)
                    .where(
                        CatalogImportJob.post_id == post.id,
                        CatalogImportCandidate.status.in_(EDITABLE_STATUSES),
                    )
                )
            ).scalars().all()
            for item in candidates:
                item.status = "superseded"
            post.version += 1
            post.status = "received"
            job = CatalogImportJob(
                shop_id=shop_id,
                post_id=post.id,
                post_version=post.version,
                status="queued",
                available_at=_utcnow(),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job.id

    @staticmethod
    async def stats(shop_id: int) -> dict:
        month_start = _utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        async with async_session() as session:
            statuses = (
                await session.execute(
                    select(CatalogImportCandidate.status, func.count())
                    .where(CatalogImportCandidate.shop_id == shop_id)
                    .group_by(CatalogImportCandidate.status)
                )
            ).all()
            prefilter = (
                await session.execute(
                    select(PrefilterFeedback.prefilter_label, func.count())
                    .where(PrefilterFeedback.shop_id == shop_id)
                    .group_by(PrefilterFeedback.prefilter_label)
                )
            ).all()
            usage = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(CatalogAnalysisRun.input_tokens), 0),
                        func.coalesce(func.sum(CatalogAnalysisRun.output_tokens), 0),
                        func.coalesce(func.sum(CatalogAnalysisRun.cost_microusd), 0),
                    ).where(
                        CatalogAnalysisRun.shop_id == shop_id,
                        CatalogAnalysisRun.created_at >= month_start,
                    )
                )
            ).one()
            jobs = (
                await session.execute(
                    select(CatalogImportJob.status, func.count())
                    .where(CatalogImportJob.shop_id == shop_id)
                    .group_by(CatalogImportJob.status)
                )
            ).all()
            posts = (
                await session.execute(
                    select(ChannelPost.status, func.count())
                    .where(ChannelPost.shop_id == shop_id)
                    .group_by(ChannelPost.status)
                )
            ).all()
            button_jobs = (
                await session.execute(
                    select(ChannelPostButtonJob.status, func.count())
                    .where(ChannelPostButtonJob.shop_id == shop_id)
                    .group_by(ChannelPostButtonJob.status)
                )
            ).all()
            ai_runs = (
                await session.execute(
                    select(func.count(func.distinct(CatalogAnalysisRun.job_id))).where(
                        CatalogAnalysisRun.shop_id == shop_id,
                        CatalogAnalysisRun.run_type == "cloud_ai",
                    )
                )
            ).scalar_one()
            ai_non_product = (
                await session.execute(
                    select(func.count(func.distinct(CatalogAnalysisRun.job_id)))
                    .join(
                        CatalogImportJob,
                        CatalogImportJob.id == CatalogAnalysisRun.job_id,
                    )
                    .join(ChannelPost, ChannelPost.id == CatalogImportJob.post_id)
                    .where(
                        CatalogAnalysisRun.shop_id == shop_id,
                        CatalogAnalysisRun.run_type == "cloud_ai",
                        ChannelPost.status == "non_product",
                    )
                )
            ).scalar_one()
        budget_microusd = int(settings.channel_import_budget_usd * 1_000_000)
        return {
            "candidates": dict(statuses),
            "prefilter": dict(prefilter),
            "jobs": dict(jobs),
            "posts": dict(posts),
            "button_jobs": dict(button_jobs),
            "ai": {
                "input_tokens": usage[0],
                "output_tokens": usage[1],
                "cost_usd": round(usage[2] / 1_000_000, 6),
                "budget_usd": settings.channel_import_budget_usd,
                "runs": ai_runs,
                "non_product": ai_non_product,
                "budget_percent": round(usage[2] / budget_microusd * 100, 1)
                if budget_microusd else 100,
            },
        }

    @staticmethod
    async def cleanup_raw_data(days: int = 90) -> int:
        cutoff = _utcnow() - timedelta(days=days)
        async with async_session() as session:
            posts = (
                await session.execute(
                    select(ChannelPost)
                    .join(CatalogImportJob, CatalogImportJob.post_id == ChannelPost.id)
                    .outerjoin(
                        CatalogImportCandidate,
                        CatalogImportCandidate.job_id == CatalogImportJob.id,
                    )
                    .where(
                        ChannelPost.updated_at < cutoff,
                        or_(
                            ChannelPost.status == "non_product",
                            CatalogImportCandidate.status == "rejected",
                        ),
                    )
                )
            ).scalars().unique().all()
            for post in posts:
                post.text = None
                post.raw_data = None
                media = (
                    await session.execute(
                        select(ChannelPostMedia).where(ChannelPostMedia.post_id == post.id)
                    )
                ).scalars().all()
                for item in media:
                    await session.delete(item)
            await session.commit()
            return len(posts)
