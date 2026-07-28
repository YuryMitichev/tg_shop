from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.catalog_service import CatalogService


async def get_catalog_keyboard():

    builder = InlineKeyboardBuilder()

    for category in await CatalogService.get_categories():

        builder.button(
            text=category["name"],
            callback_data=f"category_{category['id']}"
        )

    builder.button(
        text="⬅ Главное меню",
        callback_data="menu"
    )

    builder.adjust(1)

    return builder.as_markup()
