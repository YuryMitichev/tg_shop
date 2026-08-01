from datetime import datetime
from typing import Sequence

from sqlalchemy import select, func, or_

from app.database.db import async_session
from app.models.broadcast import Broadcast
from app.models.user_profile import UserProfile
from app.models.order import Order
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.product_photo import ProductPhoto


AUTO_TAGS = {
    "buyer": "🛒 Покупал",
    "regular": "🔥 Постоянный",
    "vip": "💎 VIP",
    "newbie": "🆕 Новичок",
}

VIP_THRESHOLD = 5000
REGULAR_ORDERS = 3


class BroadcastService:

    @staticmethod
    def _parse_tags(tags_str: str | None) -> list[str]:
        if not tags_str:
            return []
        return [t.strip() for t in tags_str.split(",") if t.strip()]

    @staticmethod
    async def auto_tag_all_users() -> int:
        """Проставляет автоматические теги всем пользователям на основе их истории заказов."""
        async with async_session() as session:
            profiles_result = await session.execute(select(UserProfile))
            profiles = profiles_result.scalars().all()
            updated = 0

            for p in profiles:
                stats = await session.execute(
                    select(
                        func.count(Order.id).label("orders"),
                        func.coalesce(func.sum(Order.total_amount), 0).label("spent"),
                    ).where(
                        Order.telegram_user_id == p.telegram_user_id,
                        Order.status != "cancelled",
                    )
                )
                row = stats.one()
                orders_count = row[0]
                total_spent = row[1]

                existing_tags = set(BroadcastService._parse_tags(p.tags))
                auto_tag_values = set(AUTO_TAGS.values())

                manual_tags = existing_tags - auto_tag_values
                new_tags = set(manual_tags)

                if orders_count >= REGULAR_ORDERS:
                    new_tags.add(AUTO_TAGS["regular"])
                if total_spent >= VIP_THRESHOLD:
                    new_tags.add(AUTO_TAGS["vip"])
                if orders_count > 0:
                    new_tags.add(AUTO_TAGS["buyer"])
                if orders_count == 0:
                    new_tags.add(AUTO_TAGS["newbie"])

                if new_tags != existing_tags:
                    p.tags = ", ".join(sorted(new_tags)) if new_tags else None
                    updated += 1

            if updated:
                await session.commit()
            return updated

    @staticmethod
    async def preview_recipients(tags: list[str] | None = None) -> dict:
        """Возвращает количество получателей по выбранным тегам."""
        async with async_session() as session:
            query = select(UserProfile.telegram_user_id)
            if tags:
                conditions = [UserProfile.tags.ilike(f"%{t}%") for t in tags]
                query = query.where(or_(*conditions))
            result = await session.execute(query)
            tg_ids = [r[0] for r in result.all()]
            return {"recipients_count": len(tg_ids), "telegram_ids": tg_ids}

    @staticmethod
    async def create_broadcast(
        product_id: int,
        discount_percent: int,
        filter_tags: list[str] | None = None,
        variant_id: int | None = None,
        message_text: str | None = None,
        created_by: int | None = None,
    ) -> Broadcast:
        async with async_session() as session:
            product = await session.get(Product, product_id)
            if product is None:
                raise ValueError("Товар не найден")

            original_price = 0
            variant_volume = None

            if variant_id:
                variant = await session.get(ProductVariant, variant_id)
                if variant and variant.product_id == product_id:
                    original_price = variant.price
                    variant_volume = variant.volume
            else:
                variants_result = await session.execute(
                    select(ProductVariant)
                    .where(ProductVariant.product_id == product_id)
                    .order_by(ProductVariant.price.asc())
                    .limit(1)
                )
                variant = variants_result.scalars().first()
                if variant:
                    original_price = variant.price
                    variant_volume = variant.volume

            discounted_price = int(original_price * (100 - discount_percent) / 100)

            tags_str = ", ".join(filter_tags) if filter_tags else None

            preview = await BroadcastService.preview_recipients(filter_tags)

            broadcast = Broadcast(
                product_id=product_id,
                product_name=product.name,
                variant_id=variant_id,
                variant_volume=variant_volume,
                original_price=original_price,
                discount_percent=discount_percent,
                discounted_price=discounted_price,
                message_text=message_text,
                filter_tags=tags_str,
                recipients_count=preview["recipients_count"],
                created_by=created_by,
            )
            session.add(broadcast)
            await session.commit()
            await session.refresh(broadcast)
            return broadcast

    @staticmethod
    async def send_broadcast(broadcast_id: int, bot) -> dict:
        """Отправляет рассылку всем подходящим получателям."""
        from app.services.crm_service import CrmService
        from app.services.offer_service import OfferService

        async with async_session() as session:
            broadcast = await session.get(Broadcast, broadcast_id)
            if broadcast is None:
                return {"ok": False, "error": "Рассылка не найдена"}

            if broadcast.status == "sent":
                return {"ok": False, "error": "Рассылка уже отправлена"}

            broadcast.status = "sending"
            await session.commit()

            tags = BroadcastService._parse_tags(broadcast.filter_tags)
            preview = await BroadcastService.preview_recipients(tags)
            tg_ids = preview["telegram_ids"]

            sent = 0
            failed = 0

            photo = await session.execute(
                select(ProductPhoto.file_id)
                .where(ProductPhoto.product_id == broadcast.product_id)
                .order_by(ProductPhoto.position)
                .limit(1)
            )
            photo_file_id = photo.scalar_one_or_none()

            discount_info = ""
            if broadcast.discount_percent > 0:
                discount_info = (
                    f"\n\n🎁 Скидка <b>{broadcast.discount_percent}%</b>!\n"
                    f"❌ Было: <s>{broadcast.original_price}₽</s>\n"
                    f"✅ Стало: <b>{broadcast.discounted_price}₽</b>"
                )

            custom_text = ""
            if broadcast.message_text:
                custom_text = f"\n\n💬 {broadcast.message_text}"

            text = (
                f"🔥 <b>Специальное предложение!</b>\n\n"
                f"📦 <b>{broadcast.product_name}</b>"
            )
            if broadcast.variant_volume:
                text += f" ({broadcast.variant_volume})"
            text += discount_info
            text += custom_text
            text += "\n\n🛒 Откройте каталог, чтобы заказать!"

            for tg_id in tg_ids:
                try:
                    if photo_file_id:
                        await bot.send_photo(tg_id, photo_file_id, caption=text)
                    else:
                        await bot.send_message(tg_id, text)
                    sent += 1

                    if broadcast.discount_percent > 0:
                        await OfferService.create_offer(
                            telegram_user_id=tg_id,
                            product_id=broadcast.product_id,
                            discount_percent=broadcast.discount_percent,
                            variant_id=broadcast.variant_id,
                            broadcast_id=broadcast.id,
                        )

                    await CrmService.log_message(
                        telegram_user_id=tg_id,
                        direction="out",
                        message_type="broadcast",
                        text=text[:500],
                        admin_id=broadcast.created_by,
                    )
                except Exception:
                    failed += 1

            broadcast.sent_count = sent
            broadcast.failed_count = failed
            broadcast.status = "sent"
            broadcast.completed_at = datetime.now()
            await session.commit()

            return {"ok": True, "sent": sent, "failed": failed}

    @staticmethod
    def _to_dict(broadcast: Broadcast) -> dict:
        return {
            "id": broadcast.id,
            "product_id": broadcast.product_id,
            "product_name": broadcast.product_name,
            "variant_id": broadcast.variant_id,
            "variant_volume": broadcast.variant_volume,
            "original_price": broadcast.original_price,
            "discount_percent": broadcast.discount_percent,
            "discounted_price": broadcast.discounted_price,
            "message_text": broadcast.message_text,
            "filter_tags": BroadcastService._parse_tags(broadcast.filter_tags),
            "status": broadcast.status,
            "recipients_count": broadcast.recipients_count,
            "sent_count": broadcast.sent_count,
            "failed_count": broadcast.failed_count,
            "created_by": broadcast.created_by,
            "created_at": broadcast.created_at.isoformat() if broadcast.created_at else None,
            "completed_at": broadcast.completed_at.isoformat() if broadcast.completed_at else None,
        }

    @staticmethod
    async def get_broadcasts(page: int = 1, per_page: int = 20) -> dict:
        async with async_session() as session:
            query = select(Broadcast).order_by(Broadcast.id.desc())
            count_query = select(func.count()).select_from(query.subquery())
            total = (await session.execute(count_query)).scalar() or 0
            result = await session.execute(
                query.offset((page - 1) * per_page).limit(per_page)
            )
            broadcasts = [BroadcastService._to_dict(b) for b in result.scalars().all()]
            return {"broadcasts": broadcasts, "total": total, "page": page, "per_page": per_page}

    @staticmethod
    async def get_broadcast(broadcast_id: int) -> dict | None:
        async with async_session() as session:
            broadcast = await session.get(Broadcast, broadcast_id)
            if broadcast is None:
                return None
            return BroadcastService._to_dict(broadcast)
