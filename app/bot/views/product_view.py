from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.product import get_product_keyboard

from app.services.catalog_service import CatalogService
from app.utils.product_card import ProductCard
from app.bot.utils.messages import track_message


async def show_product(
    callback: CallbackQuery,
    state: FSMContext,
    product: dict,
    variant_id: int | None = None,
):
    """
    Отображает карточку товара.

    Поддерживает фото: если у товара есть фотографии,
    показывает как фото-сообщение (send_photo / edit_media).
    Иначе — текстовое (edit_text / send_message).
    """

    data = await state.get_data()

    category_id = data["category_id"]

    if variant_id is not None:
        variant = CatalogService.get_variant(product, variant_id) or CatalogService.get_first_variant(product)
    else:
        variant = CatalogService.get_first_variant(product)

    await state.update_data(
        product_id=product["id"],
        variant_id=variant["id"]
    )

    position, total = await CatalogService.get_product_position(
        1,
        category_id,
        product["id"]
    )

    text = await ProductCard.render(product, variant["id"])

    keyboard = get_product_keyboard(
        product,
        variant["id"],
        position,
        total
    )

    photo_file_id = product["photos"][0]["file_id"] if product.get("photos") else None

    msg = callback.message

    if photo_file_id:
        if msg.photo:
            try:
                await msg.edit_media(
                    InputMediaPhoto(media=photo_file_id, caption=text),
                    reply_markup=keyboard,
                )
            except TelegramBadRequest:
                pass
        else:
            try:
                await msg.delete()
            except TelegramBadRequest:
                pass

            new_msg = await msg.answer_photo(
                photo=photo_file_id,
                caption=text,
                reply_markup=keyboard,
            )
            await track_message(state, new_msg)
    else:
        if msg.photo:
            try:
                await msg.delete()
            except TelegramBadRequest:
                pass

            new_msg = await msg.answer(
                text=text,
                reply_markup=keyboard,
            )
            await track_message(state, new_msg)
        else:
            try:
                await msg.edit_text(text, reply_markup=keyboard)
            except TelegramBadRequest:
                new_msg = await msg.answer(
                    text=text,
                    reply_markup=keyboard,
                )
                await track_message(state, new_msg)

    await callback.answer()
