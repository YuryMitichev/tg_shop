from datetime import datetime

from sqlalchemy import select, or_

from app.database.db import async_session
from app.models.user_offer import UserOffer


class OfferService:

    @staticmethod
    async def create_offer(
        shop_id: int,
        telegram_user_id: int,
        product_id: int,
        discount_percent: int,
        variant_id: int | None = None,
        broadcast_id: int | None = None,
        expires_at: datetime | None = None,
    ) -> UserOffer:
        async with async_session() as session:
            offer = UserOffer(
                shop_id=shop_id,
                telegram_user_id=telegram_user_id,
                product_id=product_id,
                discount_percent=discount_percent,
                variant_id=variant_id,
                broadcast_id=broadcast_id,
                expires_at=expires_at,
                is_active=True,
            )
            session.add(offer)
            await session.commit()
            await session.refresh(offer)
            return offer

    @staticmethod
    async def get_best_offer(
        shop_id: int,
        telegram_user_id: int,
        product_id: int,
        variant_id: int | None = None,
    ) -> UserOffer | None:
        """Возвращает лучшую активную и не истёкшую скидку."""
        async with async_session() as session:
            now = datetime.now()
            query = select(UserOffer).where(
                UserOffer.shop_id == shop_id,
                UserOffer.telegram_user_id == telegram_user_id,
                UserOffer.product_id == product_id,
                UserOffer.is_active == True,  # noqa: E712
                or_(
                    UserOffer.expires_at.is_(None),
                    UserOffer.expires_at > now,
                ),
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
                if variant_id and o.variant_id == variant_id and best.variant_id is None:
                    best = o

            return best

    @staticmethod
    def calc_discounted_price(price: int, discount_percent: int) -> int:
        return int(price * (100 - discount_percent) / 100)

    @staticmethod
    async def apply_to_variants(
        shop_id: int,
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
                shop_id, telegram_user_id, product_id, v["id"]
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
                    "offer_expires_at": offer.expires_at.isoformat() if offer.expires_at else None,
                })
            else:
                result.append(v)
        return result

    @staticmethod
    async def mark_used(
        shop_id: int,
        telegram_user_id: int,
        product_id: int,
        variant_id: int,
    ) -> None:
        """Помечает offer как использованный после заказа."""
        async with async_session() as session:
            now = datetime.now()
            query = select(UserOffer).where(
                UserOffer.shop_id == shop_id,
                UserOffer.telegram_user_id == telegram_user_id,
                UserOffer.product_id == product_id,
                UserOffer.is_active == True,  # noqa: E712
                or_(
                    UserOffer.expires_at.is_(None),
                    UserOffer.expires_at > now,
                ),
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

            if offers:
                best = offers[0]
                for o in offers[1:]:
                    if variant_id and o.variant_id == variant_id and best.variant_id is None:
                        best = o
                best.is_active = False
                best.used_at = datetime.now()
                await session.commit()

    @staticmethod
    async def get_user_offers(shop_id: int, telegram_user_id: int) -> list[dict]:
        """Активные предложения пользователя для Mini App."""
        async with async_session() as session:
            now = datetime.now()
            result = await session.execute(
                select(UserOffer).where(
                    UserOffer.shop_id == shop_id,
                    UserOffer.telegram_user_id == telegram_user_id,
                    UserOffer.is_active == True,  # noqa: E712
                    or_(
                        UserOffer.expires_at.is_(None),
                        UserOffer.expires_at > now,
                    ),
                )
            )
            return [
                {
                    "product_id": o.product_id,
                    "variant_id": o.variant_id,
                    "discount_percent": o.discount_percent,
                    "expires_at": o.expires_at.isoformat() if o.expires_at else None,
                }
                for o in result.scalars().all()
            ]
