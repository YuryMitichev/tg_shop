from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from app.bot.views.product_view import show_product
from app.services.catalog_service import CatalogService
from app.services.cart_service import CartService

router = Router()


@router.callback_query(F.data.startswith("variant:"))
async def select_variant(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Переключение объёма/варианта на карточке товара."""

    variant_id = int(callback.data.split(":")[1])

    data = await state.get_data()

    product_id = data.get("product_id")

    if not product_id:
        await callback.answer("Товар не найден, откройте каталог заново.", show_alert=True)
        return

    product = await CatalogService.get_product(product_id)

    if product is None:
        await callback.answer("Товар больше не найден.", show_alert=True)
        return

    await show_product(
        callback,
        state,
        product,
        variant_id=variant_id,
    )


@router.callback_query(F.data == "add_to_cart")
async def add_to_cart(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Добавление текущего товара (с выбранным вариантом) в корзину."""

    data = await state.get_data()

    product_id = data.get("product_id")
    variant_id = data.get("variant_id")

    if not product_id or not variant_id:
        await callback.answer("Сначала выберите товар.", show_alert=True)
        return

    await CartService.add_item(
        telegram_user_id=callback.from_user.id,
        product_id=product_id,
        variant_id=variant_id,
        quantity=1,
    )

    await callback.answer("Добавлено в корзину ✅")
