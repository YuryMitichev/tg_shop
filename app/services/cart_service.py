from sqlalchemy import select

from app.database.db import async_session
from app.models.cart_item import CartItem
from app.models.product import Product
from app.models.product_variant import ProductVariant


class CartService:

    @staticmethod
    async def add_item(
        telegram_user_id: int,
        product_id: int,
        variant_id: int,
        quantity: int = 1,
    ) -> None:
        """Добавить товар в корзину (или увеличить количество, если уже есть)."""
        async with async_session() as session:
            result = await session.execute(
                select(CartItem).where(
                    CartItem.telegram_user_id == telegram_user_id,
                    CartItem.product_id == product_id,
                    CartItem.variant_id == variant_id,
                )
            )
            item = result.scalar_one_or_none()

            if item:
                item.quantity += quantity
            else:
                session.add(CartItem(
                    telegram_user_id=telegram_user_id,
                    product_id=product_id,
                    variant_id=variant_id,
                    quantity=quantity,
                ))

            await session.commit()

    @staticmethod
    async def get_items(telegram_user_id: int) -> list[dict]:
        """Содержимое корзины с текущими данными о товаре (название, объём, цена)."""
        async with async_session() as session:
            result = await session.execute(
                select(CartItem, Product, ProductVariant)
                .join(Product, CartItem.product_id == Product.id)
                .join(ProductVariant, CartItem.variant_id == ProductVariant.id)
                .where(CartItem.telegram_user_id == telegram_user_id)
                .order_by(CartItem.id)
            )

            items = []

            for cart_item, product, variant in result.all():
                items.append({
                    "cart_item_id": cart_item.id,
                    "product_id": product.id,
                    "product_name": product.name,
                    "variant_id": variant.id,
                    "volume": variant.volume,
                    "price": variant.price,
                    "quantity": cart_item.quantity,
                    "subtotal": variant.price * cart_item.quantity,
                })

            return items

    @staticmethod
    async def change_quantity(telegram_user_id: int, cart_item_id: int, delta: int) -> None:
        """Изменить количество; при уходе в 0 и меньше — удалить позицию."""
        async with async_session() as session:
            item = await session.get(CartItem, cart_item_id)

            if not item or item.telegram_user_id != telegram_user_id:
                return

            item.quantity += delta

            if item.quantity <= 0:
                await session.delete(item)

            await session.commit()

    @staticmethod
    async def remove_item(telegram_user_id: int, cart_item_id: int) -> None:
        async with async_session() as session:
            item = await session.get(CartItem, cart_item_id)

            if item and item.telegram_user_id == telegram_user_id:
                await session.delete(item)
                await session.commit()

    @staticmethod
    async def clear(telegram_user_id: int) -> None:
        async with async_session() as session:
            result = await session.execute(
                select(CartItem).where(CartItem.telegram_user_id == telegram_user_id)
            )

            for item in result.scalars().all():
                await session.delete(item)

            await session.commit()
