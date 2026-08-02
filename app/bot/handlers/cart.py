from aiogram import Router, F
from app.bot.shop_context import get_shop_id
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.cart import get_cart_keyboard
from app.bot.utils.messages import show_screen, replace_with_text
from app.services.cart_service import CartService
from app.services.message_service import MessageService


def setup_router() -> Router:
    router = Router()

    async def _render_cart_text(items: list[dict]) -> str:
        if not items:
            return await MessageService.get(get_shop_id(), "cart_empty")

        lines = ["🛒 <b>Ваша корзина</b>\n"]

        total = 0

        for item in items:
            lines.append(
                f"{item['product_name']} ({item['volume']}) "
                f"— {item['price']} ₽ × {item['quantity']} = {item['subtotal']} ₽"
            )
            total += item["subtotal"]

        lines.append(f"\n💰 Итого: <b>{total} ₽</b>")

        return "\n".join(lines)

    async def _render_cart_cb(callback: CallbackQuery, state: FSMContext) -> None:
        items = await CartService.get_items(get_shop_id(), callback.from_user.id)

        await replace_with_text(
            callback.message,
            callback.bot,
            callback.message.chat.id,
            state,
            await _render_cart_text(items),
            reply_markup=get_cart_keyboard(items),
        )

        await callback.answer()

    @router.message(F.text == "🛒 Корзина")
    async def open_cart_msg(message: Message, state: FSMContext):
        await state.clear()

        items = await CartService.get_items(get_shop_id(), message.from_user.id)

        await show_screen(
            message,
            state,
            await _render_cart_text(items),
            reply_markup=get_cart_keyboard(items),
        )

    @router.callback_query(F.data == "cart")
    async def open_cart_cb(callback: CallbackQuery, state: FSMContext):
        await _render_cart_cb(callback, state)

    @router.callback_query(F.data.startswith("cart_inc:"))
    async def increase_quantity(callback: CallbackQuery):
        cart_item_id = int(callback.data.split(":")[1])

        await CartService.change_quantity(get_shop_id(), callback.from_user.id, cart_item_id, +1)

        items = await CartService.get_items(get_shop_id(), callback.from_user.id)

        await callback.message.edit_text(
            await _render_cart_text(items),
            reply_markup=get_cart_keyboard(items)
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("cart_dec:"))
    async def decrease_quantity(callback: CallbackQuery):
        cart_item_id = int(callback.data.split(":")[1])

        await CartService.change_quantity(get_shop_id(), callback.from_user.id, cart_item_id, -1)

        items = await CartService.get_items(get_shop_id(), callback.from_user.id)

        await callback.message.edit_text(
            await _render_cart_text(items),
            reply_markup=get_cart_keyboard(items)
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("cart_remove:"))
    async def remove_item(callback: CallbackQuery):
        cart_item_id = int(callback.data.split(":")[1])

        await CartService.remove_item(get_shop_id(), callback.from_user.id, cart_item_id)

        items = await CartService.get_items(get_shop_id(), callback.from_user.id)

        await callback.message.edit_text(
            await _render_cart_text(items),
            reply_markup=get_cart_keyboard(items)
        )
        await callback.answer()

    return router
