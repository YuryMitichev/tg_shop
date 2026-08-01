from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from app.bot.views.product_view import show_product
from app.bot.keyboards.catalog import get_catalog_keyboard
from app.bot.utils.messages import show_screen, replace_with_text
from app.services.catalog_service import CatalogService
from app.services.message_service import MessageService

router = Router()

SHOP_ID = 1


async def _render_catalog(callback: CallbackQuery, state: FSMContext) -> None:
    keyboard = await get_catalog_keyboard()
    text = await MessageService.get(SHOP_ID, "catalog")

    await replace_with_text(
        callback.message,
        callback.bot,
        callback.message.chat.id,
        state,
        text,
        reply_markup=keyboard,
    )

    await callback.answer()


@router.message(F.text == "🛍 Каталог")
async def open_catalog_msg(message: Message, state: FSMContext):
    await state.clear()

    keyboard = await get_catalog_keyboard()
    text = await MessageService.get(SHOP_ID, "catalog")

    await show_screen(
        message,
        state,
        text,
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "catalog")
async def open_catalog_cb(callback: CallbackQuery, state: FSMContext):
    await _render_catalog(callback, state)


@router.callback_query(F.data.startswith("category_"))
async def open_category(
    callback: CallbackQuery,
    state: FSMContext
):
    category_id = int(callback.data.split("_")[1])

    product = await CatalogService.get_first_product(SHOP_ID, category_id)

    if product is None:
        await callback.answer(
            "В этой категории пока нет товаров.",
            show_alert=True
        )
        return

    await state.update_data(
        category_id=category_id
    )

    await show_product(
        callback,
        state,
        product
    )


@router.callback_query(F.data == "next_product")
async def next_product(
    callback: CallbackQuery,
    state: FSMContext
):
    data = await state.get_data()

    product = await CatalogService.get_next_product(
        SHOP_ID,
        data["category_id"],
        data["product_id"]
    )

    await show_product(
        callback,
        state,
        product
    )


@router.callback_query(F.data == "prev_product")
async def prev_product(
    callback: CallbackQuery,
    state: FSMContext
):
    data = await state.get_data()

    product = await CatalogService.get_previous_product(
        SHOP_ID,
        data["category_id"],
        data["product_id"]
    )

    await show_product(
        callback,
        state,
        product
    )


@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()
