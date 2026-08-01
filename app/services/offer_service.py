from datetime import datetime

from sqlalchemy import select

from app.database.db import async_session
from app.models.user_offer import UserOffer


class OfferService:

    @staticmethod
    async def create_offer(
        telegram_user_id: int,
        product_id: int,
        discount_percent: int,
        variant_id: int | None = None,
        broadcast_id: int | None = None,
    ) -> UserOffer:
        async with async_session() as session:
            offer = UserOffer(
                telegram_user_id=telegram_user_id,
                product_id=product_id,
                discount_percent=discount_percent,
                variant_id=variant_id,
                broadcast_id=broadcast_id,
                is_active=True,
            )
            session.add(offer)
            await session.commit()
            await session.refresh(offer)
            return offer

    @staticmethod
    async def get_best_offer(
        telegram_user_id: int,
        product_id: int,
        variant_id: int | None = None,
    ) -> UserOffer | None:
        """Возвращает лучшую активную скидку для товара/варианта пользователя."""
        async with async_session() as session:
            query = select(UserOffer).where(
                UserOffer.telegram_user_id == telegram_user_id,
                UserOffer.product_id == product_id,
                UserOffer.is_active == True,  # noqa: E712
            )

            if variant_id:
                query = query.where(
                    (UserOffer.variant_id == variant_id)
                    | (UserOffer.variant_id.is_(None))
                )

            result = await session.execute(
                query.order_by(UserOffer.discount_percent.desc())
            )
            offers = result.scalars().all()

            if not offers:
                return None

            best = offers[0]
            for o in offers[1:]:
                if o.variant_id == variant_id and best.variant_id is None:
                    best = o

            return best

    @staticmethod
    def calc_discounted_price(price: int, discount_percent: int) -> int:
        return int(price * (100 - discount_percent) / 100)

    @staticmethod
    async def apply_to_variants(
        telegram_user_id: int | None,
        product_id: int,
        variants: list[dict],
    ) -> list[dict]:
        """Применяет персональные скидки к списку вариантов товара."""
        if not telegram_user_id:
            return variants

        result = []
        for v in variants:
            offer = await OfferService.get_best_offer(
                telegram_user_id, product_id, v["id"]
            )
            if offer and offer.discount_percent > 0:
                original = v["price"]
                discounted = OfferService.calc_discounted_price(
                    original, offer.discount_percent
                )
                result.append({
                    **v,
                    "original_price": original,
                    "price": discounted,
                    "discount_percent": offer.discount_percent,
                })
            else:
                result.append(v)
        return result

    @staticmethod
    async def mark_used(
        telegram_user_id: int,
        product_id: int,
        variant_id: int,
    ) -> None:
        """Помечает offer как использованный после заказа."""
        async with async_session() as session:
            offer = await OfferService.get_best_offer(
                telegram_user_id, product_id, variant_id
            )
            if offer:
                offer.is_active = False
                offer.used_at = datetime.now()
                await session.commit()
