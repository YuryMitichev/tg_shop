from sqlalchemy import select

from app.database.db import async_session
from app.models.cart_item import CartItem
from app.models.product import Product
from app.models.product_variant import ProductVariant


class CartService:

    @staticmethod
    async def add_item(
        shop_id: int,
        telegram_user_id: int,
        product_id: int,
        variant_id: int,
        quantity: int = 1,
    ) -> str | None:
        """Добавить товар в корзину (или увеличить количество, если уже есть).

        Возвращает None при успехе, либо сообщение об ошибке (нет в наличии).
        """
        async with async_session() as session:
            result = await session.execute(
                select(ProductVariant).where(
                    ProductVariant.shop_id == shop_id,
                    ProductVariant.id == variant_id,
                )
            )
            variant = result.scalar_one_or_none()

            if variant and variant.stock == 0:
                return "Этого товара нет в наличии"

            result = await session.execute(
                select(CartItem).where(
                    CartItem.shop_id == shop_id,
                    CartItem.telegram_user_id == telegram_user_id,
                    CartItem.product_id == product_id,
                    CartItem.variant_id == variant_id,
                )
            )
            item = result.scalar_one_or_none()

            new_quantity = (item.quantity if item else 0) + quantity

            if variant and variant.stock > 0 and new_quantity > variant.stock:
                return f"На складе осталось только {variant.stock} шт."

            if item:
                item.quantity += quantity
            else:
                session.add(CartItem(
                    shop_id=shop_id,
                    telegram_user_id=telegram_user_id,
                    product_id=product_id,
                    variant_id=variant_id,
                    quantity=quantity,
                ))

            await session.commit()
            return None

    @staticmethod
    async def check_availability(shop_id: int, telegram_user_id: int) -> list[dict] | None:
        """Проверить доступность всех товаров в корзине по текущим остаткам.

        Возвращает список недоступных позиций или None, если всё в наличии.
        """
        async with async_session() as session:
            result = await session.execute(
                select(CartItem, Product, ProductVariant)
                .join(Product, CartItem.product_id == Product.id)
                .join(ProductVariant, CartItem.variant_id == ProductVariant.id)
                .where(
                    CartItem.shop_id == shop_id,
                    CartItem.telegram_user_id == telegram_user_id,
                )
            )

            unavailable: list[dict] = []

            for cart_item, product, variant in result.all():
                if variant.stock < cart_item.quantity:
                    unavailable.append({
                        "product_name": product.name,
                        "volume": variant.volume,
                        "requested": cart_item.quantity,
                        "available": variant.stock,
                    })

            return unavailable if unavailable else None

    @staticmethod
    async def get_items(shop_id: int, telegram_user_id: int) -> list[dict]:
        """Содержимое корзины с текущими данными о товаре (название, объём, цена).

        Применяет персональные скидки (UserOffer), если они есть.
        """
        from app.services.offer_service import OfferService

        async with async_session() as session:
            result = await session.execute(
                select(CartItem, Product, ProductVariant)
                .join(Product, CartItem.product_id == Product.id)
                .join(ProductVariant, CartItem.variant_id == ProductVariant.id)
                .where(
                    CartItem.shop_id == shop_id,
                    CartItem.telegram_user_id == telegram_user_id,
                )
                .order_by(CartItem.id)
            )

            items = []

            for cart_item, product, variant in result.all():
                price = variant.price
                original_price = None
                discount_percent = 0

                offer = await OfferService.get_best_offer(
                    shop_id, telegram_user_id, product.id, variant.id
                )
                if offer and offer.discount_percent > 0:
                    original_price = variant.price
                    price = OfferService.calc_discounted_price(
                        variant.price, offer.discount_percent
                    )
                    discount_percent = offer.discount_percent

                items.append({
                    "cart_item_id": cart_item.id,
                    "product_id": product.id,
                    "product_name": product.name,
                    "variant_id": variant.id,
                    "volume": variant.volume,
                    "price": price,
                    "original_price": original_price,
                    "discount_percent": discount_percent,
                    "quantity": cart_item.quantity,
                    "stock": variant.stock,
                    "subtotal": price * cart_item.quantity,
                })

            return items

    @staticmethod
    async def change_quantity(shop_id: int, telegram_user_id: int, cart_item_id: int, delta: int) -> str | None:
        """Изменить количество; при уходе в 0 и меньше — удалить позицию.

        Возвращает None при успехе, либо сообщение об ошибке (превышен остаток).
        """
        async with async_session() as session:
            result = await session.execute(
                select(CartItem).where(
                    CartItem.shop_id == shop_id,
                    CartItem.id == cart_item_id,
                    CartItem.telegram_user_id == telegram_user_id,
                )
            )
            item = result.scalar_one_or_none()

            if not item:
                return None

            new_quantity = item.quantity + delta

            if new_quantity <= 0:
                await session.delete(item)
                await session.commit()
                return None

            variant_result = await session.execute(
                select(ProductVariant).where(ProductVariant.id == item.variant_id)
            )
            variant = variant_result.scalar_one_or_none()

            if variant and variant.stock > 0 and new_quantity > variant.stock:
                return f"На складе осталось только {variant.stock} шт."

            item.quantity = new_quantity
            await session.commit()
            return None

    @staticmethod
    async def remove_item(shop_id: int, telegram_user_id: int, cart_item_id: int) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(CartItem).where(
                    CartItem.shop_id == shop_id,
                    CartItem.id == cart_item_id,
                    CartItem.telegram_user_id == telegram_user_id,
                )
            )
            item = result.scalar_one_or_none()

            if item:
                await session.delete(item)
                await session.commit()

    @staticmethod
    async def clear(shop_id: int, telegram_user_id: int) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(CartItem).where(
                    CartItem.shop_id == shop_id,
                    CartItem.telegram_user_id == telegram_user_id,
                )
            )

            for item in result.scalars().all():
                await session.delete(item)

            await session.commit()
