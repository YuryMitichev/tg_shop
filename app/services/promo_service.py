from datetime import datetime, timezone

from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.db import async_session
from app.models.promo_code import PromoCode


class PromoCodeService:

    @staticmethod
    async def validate(shop_id: int, code: str, cart_total: int) -> dict | None:
        """
        Проверяет промокод и возвращает информацию о скидке или None.
        Не увеличивает счётчик использований — это делается в create_order.
        """
        code = code.strip().upper()

        async with async_session() as session:
            result = await session.execute(
                select(PromoCode).where(
                    PromoCode.shop_id == shop_id,
                    PromoCode.code == code,
                )
            )
            promo = result.scalar_one_or_none()

        if promo is None:
            return None

        if not promo.is_active:
            return None

        if promo.valid_until is not None:
            if promo.valid_until < datetime.now(timezone.utc):
                return None

        if promo.max_uses is not None and promo.used_count >= promo.max_uses:
            return None

        if promo.discount_type == "percent":
            discount = cart_total * promo.discount_value // 100
        else:
            discount = min(promo.discount_value, cart_total)

        discount = min(discount, cart_total)

        return {
            "code": promo.code,
            "discount_type": promo.discount_type,
            "discount_value": promo.discount_value,
            "discount_amount": discount,
            "final_total": cart_total - discount,
        }

    @staticmethod
    async def increment_usage(shop_id: int, code: str) -> None:
        """Увеличивает счётчик использований промокода."""
        code = code.strip().upper()

        async with async_session() as session:
            await PromoCodeService.try_increment_usage(session, shop_id, code)
            await session.commit()

    @staticmethod
    async def try_increment_usage(
        session: AsyncSession, shop_id: int, code: str
    ) -> bool:
        """Атомарно инкрементирует счётчик использований.

        True — успешно, False — лимит исчерпан (кто-то успел раньше).
        Работает внутри переданной сессии (для транзакционной целостности).
        """
        code = code.strip().upper()

        result = await session.execute(
            update(PromoCode)
            .where(
                PromoCode.shop_id == shop_id,
                PromoCode.code == code,
                PromoCode.is_active == True,  # noqa: E712
                or_(
                    PromoCode.max_uses.is_(None),
                    PromoCode.used_count < PromoCode.max_uses,
                ),
            )
            .values(used_count=PromoCode.used_count + 1)
        )
        return result.rowcount > 0

    @staticmethod
    async def create(
        shop_id: int,
        code: str,
        discount_type: str,
        discount_value: int,
        max_uses: int | None = None,
        valid_until: datetime | None = None,
    ) -> int:
        """Создаёт промокод. Возвращает ID."""
        code = code.strip().upper()

        async with async_session() as session:
            promo = PromoCode(
                shop_id=shop_id,
                code=code,
                discount_type=discount_type,
                discount_value=discount_value,
                max_uses=max_uses,
                valid_until=valid_until,
            )
            session.add(promo)
            await session.commit()
            await session.refresh(promo)
            return promo.id

    @staticmethod
    async def get_all(shop_id: int) -> list[dict]:
        """Все промокоды для админки."""
        async with async_session() as session:
            result = await session.execute(
                select(PromoCode)
                .where(PromoCode.shop_id == shop_id)
                .order_by(PromoCode.id.desc())
            )
            return [
                {
                    "id": p.id,
                    "code": p.code,
                    "discount_type": p.discount_type,
                    "discount_value": p.discount_value,
                    "max_uses": p.max_uses,
                    "used_count": p.used_count,
                    "is_active": p.is_active,
                    "valid_until": p.valid_until,
                }
                for p in result.scalars().all()
            ]

    @staticmethod
    async def toggle_active(shop_id: int, promo_id: int) -> None:
        """Включить/выключить промокод."""
        async with async_session() as session:
            promo = await session.get(PromoCode, promo_id)
            if promo and promo.shop_id == shop_id:
                promo.is_active = not promo.is_active
                await session.commit()

    @staticmethod
    async def delete(shop_id: int, promo_id: int) -> None:
        """Удалить промокод."""
        async with async_session() as session:
            promo = await session.get(PromoCode, promo_id)
            if promo and promo.shop_id == shop_id:
                await session.delete(promo)
                await session.commit()
