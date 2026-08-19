from __future__ import annotations

import logging
from collections import defaultdict
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.database.db import async_session
from app.models.channel_import import (
    ChannelAttributionEvent,
    ChannelConnection,
    ChannelPost,
    ChannelPostMedia,
    ProductSourceRef,
)
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.services.sales_service import SalesService


logger = logging.getLogger(__name__)
EVENT_TYPES = {"product_open", "add_to_cart"}


class ChannelAttributionService:
    @staticmethod
    def enabled_for_shop(shop_id: int) -> bool:
        return settings.channel_attribution_enabled and (
            settings.channel_attribution_pilot_shop_id is None
            or settings.channel_attribution_pilot_shop_id == shop_id
        )

    @staticmethod
    async def resolve_source(session, shop_id: int, product_id: int, token: str):
        if not token or not ChannelAttributionService.enabled_for_shop(shop_id):
            return None
        row = (
            await session.execute(
                select(ProductSourceRef, ChannelPost)
                .join(
                    ChannelPost,
                    (ChannelPost.connection_id == ProductSourceRef.connection_id)
                    & (
                        ChannelPost.telegram_message_id
                        == ProductSourceRef.telegram_message_id
                    ),
                )
                .where(
                    ProductSourceRef.shop_id == shop_id,
                    ProductSourceRef.product_id == product_id,
                    ProductSourceRef.public_token == token,
                    ChannelPost.shop_id == shop_id,
                )
            )
        ).one_or_none()
        return row

    @staticmethod
    async def record_event(
        shop_id: int,
        telegram_user_id: int,
        product_id: int,
        source_token: str,
        event_type: str,
        event_key: str,
    ) -> bool:
        if event_type not in EVENT_TYPES or not event_key or len(event_key) > 64:
            return False
        async with async_session() as session:
            resolved = await ChannelAttributionService.resolve_source(
                session, shop_id, product_id, source_token
            )
            if resolved is None:
                return False
            ref, post = resolved
            exists = (
                await session.execute(
                    select(ChannelAttributionEvent.id).where(
                        ChannelAttributionEvent.shop_id == shop_id,
                        ChannelAttributionEvent.event_type == event_type,
                        ChannelAttributionEvent.event_key == event_key,
                    )
                )
            ).scalar_one_or_none()
            if exists is not None:
                return False
            session.add(
                ChannelAttributionEvent(
                    shop_id=shop_id,
                    post_id=post.id,
                    source_ref_id=ref.id,
                    product_id=product_id,
                    telegram_user_id=telegram_user_id,
                    event_type=event_type,
                    event_key=event_key,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
            return True

    @staticmethod
    async def publication_report(shop_id: int) -> dict:
        async with async_session() as session:
            posts = (
                await session.execute(
                    select(ChannelPost, ChannelConnection)
                    .join(ChannelConnection, ChannelConnection.id == ChannelPost.connection_id)
                    .where(
                        ChannelPost.shop_id == shop_id,
                        or_(
                            select(ProductSourceRef.id)
                            .where(
                                ProductSourceRef.shop_id == shop_id,
                                ProductSourceRef.connection_id
                                == ChannelPost.connection_id,
                                ProductSourceRef.telegram_message_id
                                == ChannelPost.telegram_message_id,
                            )
                            .exists(),
                            select(ChannelAttributionEvent.id)
                            .where(ChannelAttributionEvent.post_id == ChannelPost.id)
                            .exists(),
                            select(OrderItem.id)
                            .where(OrderItem.source_post_id == ChannelPost.id)
                            .exists(),
                        ),
                    )
                    .order_by(ChannelPost.published_at.desc(), ChannelPost.id.desc())
                )
            ).all()
            post_ids = [post.id for post, _connection in posts]
            if not post_ids:
                return {"summary": ChannelAttributionService._empty_summary(), "posts": []}

            product_rows = (
                await session.execute(
                    select(ProductSourceRef, Product)
                    .join(Product, Product.id == ProductSourceRef.product_id)
                    .join(
                        ChannelPost,
                        (ChannelPost.connection_id == ProductSourceRef.connection_id)
                        & (
                            ChannelPost.telegram_message_id
                            == ProductSourceRef.telegram_message_id
                        ),
                    )
                    .where(ChannelPost.id.in_(post_ids))
                )
            ).all()
            products_by_post: dict[int, list[str]] = defaultdict(list)
            for ref, product in product_rows:
                post_id = next(
                    post.id
                    for post, _ in posts
                    if post.connection_id == ref.connection_id
                    and post.telegram_message_id == ref.telegram_message_id
                )
                if product.name not in products_by_post[post_id]:
                    products_by_post[post_id].append(product.name)

            event_rows = (
                await session.execute(
                    select(
                        ChannelAttributionEvent.post_id,
                        ChannelAttributionEvent.event_type,
                        func.count(ChannelAttributionEvent.id),
                        func.count(func.distinct(ChannelAttributionEvent.telegram_user_id)),
                    )
                    .where(
                        ChannelAttributionEvent.shop_id == shop_id,
                        ChannelAttributionEvent.post_id.in_(post_ids),
                    )
                    .group_by(
                        ChannelAttributionEvent.post_id,
                        ChannelAttributionEvent.event_type,
                    )
                )
            ).all()
            events: dict[tuple[int, str], tuple[int, int]] = {
                (row[0], row[1]): (row[2], row[3]) for row in event_rows
            }

            orders = (
                await session.execute(
                    select(Order)
                    .options(selectinload(Order.items))
                    .join(OrderItem, OrderItem.order_id == Order.id)
                    .where(
                        Order.shop_id == shop_id,
                        SalesService.confirmed_condition(),
                        OrderItem.source_post_id.in_(post_ids),
                    )
                )
            ).scalars().unique().all()

            order_ids_by_post: dict[int, set[int]] = defaultdict(set)
            units_by_post: dict[int, int] = defaultdict(int)
            revenue_by_post: dict[int, int] = defaultdict(int)
            for order in orders:
                gross_total = sum(item.price * item.quantity for item in order.items) or 1
                for item in order.items:
                    if item.source_post_id not in post_ids:
                        continue
                    post_id = int(item.source_post_id)
                    item_gross = item.price * item.quantity
                    item_net = round(item_gross * order.total_amount / gross_total)
                    order_ids_by_post[post_id].add(order.id)
                    units_by_post[post_id] += item.quantity
                    revenue_by_post[post_id] += item_net

            media_rows = (
                await session.execute(
                    select(ChannelPostMedia.post_id, func.min(ChannelPostMedia.id))
                    .where(ChannelPostMedia.post_id.in_(post_ids))
                    .group_by(ChannelPostMedia.post_id)
                )
            ).all()
            media_by_post = {row[0]: row[1] for row in media_rows}

            result = []
            all_order_ids: set[int] = set()
            for post, connection in posts:
                total_opens, unique_opens = events.get((post.id, "product_open"), (0, 0))
                total_adds, unique_adds = events.get((post.id, "add_to_cart"), (0, 0))
                paid_orders = len(order_ids_by_post[post.id])
                all_order_ids.update(order_ids_by_post[post.id])
                views = post.telegram_views or 0
                result.append(
                    {
                        "post_id": post.id,
                        "telegram_message_id": post.telegram_message_id,
                        "published_at": post.published_at.isoformat() if post.published_at else None,
                        "text": (post.text or "")[:240],
                        "channel_title": connection.channel_title,
                        "post_url": (
                            f"https://t.me/{connection.channel_username.lstrip('@')}/"
                            f"{post.telegram_message_id}"
                            if connection.channel_username
                            else None
                        ),
                        "media_id": media_by_post.get(post.id),
                        "products": products_by_post[post.id],
                        "views": views,
                        "forwards": post.telegram_forwards or 0,
                        "views_updated_at": (
                            post.metrics_updated_at.isoformat()
                            if post.metrics_updated_at
                            else None
                        ),
                        "opens": unique_opens,
                        "total_opens": total_opens,
                        "cart_adds": unique_adds,
                        "total_cart_adds": total_adds,
                        "paid_orders": paid_orders,
                        "units_sold": units_by_post[post.id],
                        "revenue": revenue_by_post[post.id],
                        "ctr": round(unique_opens / views * 100, 1) if views else 0,
                        "purchase_conversion": (
                            round(paid_orders / unique_opens * 100, 1)
                            if unique_opens
                            else 0
                        ),
                    }
                )

            summary = {
                "views": sum(item["views"] for item in result),
                "opens": sum(item["opens"] for item in result),
                "cart_adds": sum(item["cart_adds"] for item in result),
                "paid_orders": len(all_order_ids),
                "revenue": sum(item["revenue"] for item in result),
            }
            summary["ctr"] = round(summary["opens"] / summary["views"] * 100, 1) if summary["views"] else 0
            summary["purchase_conversion"] = (
                round(summary["paid_orders"] / summary["opens"] * 100, 1)
                if summary["opens"]
                else 0
            )
            return {"summary": summary, "posts": result}

    @staticmethod
    def _empty_summary() -> dict:
        return {
            "views": 0,
            "opens": 0,
            "cart_adds": 0,
            "paid_orders": 0,
            "revenue": 0,
            "ctr": 0,
            "purchase_conversion": 0,
        }
