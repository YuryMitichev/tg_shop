from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.catalog_service import CatalogService


async def get_catalog_keyboard():

    builder = InlineKeyboardBuilder()

    for category in await CatalogService.get_categories(1):
        emoji = category.get("emoji")
        label = f"{emoji} {category['name']}" if emoji else category["name"]

        builder.button(
            text=label,
            callback_data=f"category_{category['id']}"
        )

    builder.button(
        text="⬅ Главное меню",
        callback_data="menu"
    )

    builder.adjust(1)

    return builder.as_markup()
