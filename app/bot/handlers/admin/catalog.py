from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.filters.admin import IsAdmin
from app.bot.keyboards.admin import (
    get_admin_categories_keyboard,
    get_admin_edit_keyboard,
    get_admin_manage_categories_keyboard,
    get_admin_menu,
    get_admin_photos_keyboard,
    get_admin_product_keyboard,
    get_admin_products_keyboard,
    get_admin_rename_category_keyboard,
    get_confirm_delete_category_keyboard,
    get_confirm_delete_keyboard,
    get_photos_done_keyboard,
    get_yes_no_keyboard,
)
from app.bot.shop_context import get_shop_id
from app.bot.states.admin_product import (
    AdminCategoryState,
    AdminEditProductState,
    AdminProductState,
)
from app.services.catalog_admin_service import CatalogAdminService


def setup_catalog_router() -> Router:
    router = Router()
    router.message.filter(IsAdmin())
    router.callback_query.filter(IsAdmin())

    # ==========================
    # Управление категориями
    # ==========================

    @router.callback_query(F.data == "admin_manage_categories")
    async def manage_categories(callback: CallbackQuery, state: FSMContext):
        await state.clear()

        categories = await CatalogAdminService.get_categories(get_shop_id())

        await callback.message.edit_text(
            "🗂 <b>Управление категориями</b>\n\n"
            "Нажмите на категорию, чтобы переименовать или удалить.",
            reply_markup=get_admin_manage_categories_keyboard(categories)
        )

        await callback.answer()

    @router.callback_query(F.data == "admin_add_category")
    async def add_category_start(callback: CallbackQuery, state: FSMContext):
        await state.set_state(AdminCategoryState.waiting_name)

        await callback.message.edit_text("➕ Введите название новой категории:")
        await callback.answer()

    @router.message(AdminCategoryState.waiting_name)
    async def add_category_process(message: Message, state: FSMContext):
        name = message.text.strip()

        await state.update_data(name=name)
        await state.set_state(AdminCategoryState.waiting_emoji)

        await message.answer(
            "Отправьте эмодзи для категории (например: 🕊, 🏠, 🎁).\n"
            'Отправьте «-», чтобы пропустить.'
        )

    @router.message(AdminCategoryState.waiting_emoji)
    async def process_category_emoji(message: Message, state: FSMContext):
        data = await state.get_data()
        emoji_text = message.text.strip()
        emoji = None if emoji_text == "-" else emoji_text

        if "category_id" in data:
            category_id = data["category_id"]
            await CatalogAdminService.update_category_emoji(get_shop_id(), category_id, emoji)
            await state.clear()

            categories = await CatalogAdminService.get_categories(get_shop_id())
            category = next((c for c in categories if c["id"] == category_id), None)

            emoji_display = f"{category['emoji']} " if category and category["emoji"] else ""
            await message.answer(
                f"✅ Эмодзи категории изменён.\n\n"
                "🗂 <b>Управление категориями</b>\n\n"
                "Нажмите на категорию, чтобы переименовать или удалить.",
                reply_markup=get_admin_manage_categories_keyboard(categories)
            )
        else:
            name = data["name"]
            category_id = await CatalogAdminService.create_category(get_shop_id(), name, emoji)
            await state.clear()

            categories = await CatalogAdminService.get_categories(get_shop_id())

            await message.answer(
                f"✅ Категория «{name}» добавлена (ID {category_id}).\n\n"
                "🗂 <b>Управление категориями</b>\n\n"
                "Нажмите на категорию, чтобы переименовать или удалить.",
                reply_markup=get_admin_manage_categories_keyboard(categories)
            )

    @router.callback_query(F.data.startswith("admin_emoji_cat:"))
    async def emoji_category_start(callback: CallbackQuery, state: FSMContext):
        category_id = int(callback.data.split(":")[1])

        await state.set_state(AdminCategoryState.waiting_emoji)
        await state.update_data(category_id=category_id)

        await callback.message.edit_text(
            "Отправьте новый эмодзи для категории.\n"
            'Отправьте «-», чтобы убрать эмодзи.'
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_rename_cat:"))
    async def rename_category_start(callback: CallbackQuery, state: FSMContext):
        category_id = int(callback.data.split(":")[1])

        await state.set_state(AdminCategoryState.waiting_rename)
        await state.update_data(category_id=category_id)

        categories = await CatalogAdminService.get_categories(get_shop_id())
        category = next((c for c in categories if c["id"] == category_id), None)

        if category is None:
            await callback.answer("Категория не найдена.", show_alert=True)
            return

        count = await CatalogAdminService.count_products_in_category(get_shop_id(), category_id)

        emoji_display = f"{category['emoji']} " if category["emoji"] else ""
        emoji_line = f"Эмодзи: {category['emoji']}" if category["emoji"] else "Эмодзи: нет"

        await callback.message.edit_text(
            f"✏️ <b>{emoji_display}{category['name']}</b>\n\n"
            f"Товаров в категории: {count}\n"
            f"{emoji_line}\n\n"
            "Введите новое название или воспользуйтесь кнопками ниже.",
            reply_markup=get_admin_rename_category_keyboard(category_id)
        )

        await callback.answer()

    @router.message(AdminCategoryState.waiting_rename)
    async def rename_category_process(message: Message, state: FSMContext):
        data = await state.get_data()
        category_id = data["category_id"]
        name = message.text.strip()

        await CatalogAdminService.rename_category(get_shop_id(), category_id, name)
        await state.clear()

        categories = await CatalogAdminService.get_categories(get_shop_id())

        await message.answer(
            f"✅ Категория переименована в «{name}».\n\n"
            "🗂 <b>Управление категориями</b>\n\n"
            "Нажмите на категорию, чтобы переименовать или удалить.",
            reply_markup=get_admin_manage_categories_keyboard(categories)
        )

    @router.callback_query(F.data.startswith("admin_delete_cat:"))
    async def delete_category_confirm(callback: CallbackQuery):
        category_id = int(callback.data.split(":")[1])

        count = await CatalogAdminService.count_products_in_category(get_shop_id(), category_id)

        if count > 0:
            await callback.answer(
                f"Нельзя удалить: в категории {count} товаров.",
                show_alert=True,
            )
            return

        await callback.message.edit_text(
            "Удалить категорию? Это необратимо.",
            reply_markup=get_confirm_delete_category_keyboard(category_id)
        )

        await callback.answer()

    @router.callback_query(F.data.startswith("admin_delete_cat_confirm:"))
    async def delete_category_execute(callback: CallbackQuery):
        category_id = int(callback.data.split(":")[1])

        await CatalogAdminService.delete_category(get_shop_id(), category_id)

        categories = await CatalogAdminService.get_categories(get_shop_id())

        await callback.message.edit_text(
            "✅ Категория удалена.\n\n"
            "🗂 <b>Управление категориями</b>\n\n"
            "Нажмите на категорию, чтобы переименовать или удалить.",
            reply_markup=get_admin_manage_categories_keyboard(categories)
        )

        await callback.answer("Категория удалена")

    # ==========================
    # Товары
    # ==========================

    @router.callback_query(F.data == "admin_products")
    async def show_categories(callback: CallbackQuery):
        categories = await CatalogAdminService.get_categories(get_shop_id())

        await callback.message.edit_text(
            "🗂 <b>Категории</b>\n\nВыберите категорию для управления товарами.",
            reply_markup=get_admin_categories_keyboard(categories)
        )

        await callback.answer()

    def _render_products_text(products: list[dict]) -> str:
        text = "📦 <b>Товары категории</b>\n\n"
        text += "👁 — виден покупателям, 🙈 — скрыт" if products else "Товаров пока нет."
        return text

    async def _render_products(callback: CallbackQuery, category_id: int) -> None:
        products = await CatalogAdminService.get_products(get_shop_id(), category_id)

        await callback.message.edit_text(
            _render_products_text(products),
            reply_markup=get_admin_products_keyboard(category_id, products)
        )

    @router.callback_query(F.data.startswith("admin_cat:"))
    async def show_products(callback: CallbackQuery):
        category_id = int(callback.data.split(":")[1])

        await _render_products(callback, category_id)
        await callback.answer()

    def _render_product_text(product: dict) -> str:
        lines = [f"🕯 <b>{product['name']}</b>\n", product["description"], ""]

        for variant in product["variants"]:
            burn = f", горит {variant['burn']}" if variant["burn"] else ""
            lines.append(f"• {variant['volume']} — {variant['price']} ₽{burn}")

        lines.append("")

        photo_count = len(product.get("photos", []))
        if photo_count:
            lines.append(f"📸 Фото: {photo_count} шт.")
        else:
            lines.append("📸 Фото нет")

        lines.append("")

        lines.append("Виден покупателям" if product["is_active"] else "🙈 Скрыт от покупателей")

        return "\n".join(lines)

    async def _render_product(callback: CallbackQuery, product_id: int) -> dict | None:
        product = await CatalogAdminService.get_product(get_shop_id(), product_id)

        if product is None:
            await callback.answer("Товар не найден.", show_alert=True)
            return None

        await callback.message.edit_text(
            _render_product_text(product),
            reply_markup=get_admin_product_keyboard(product)
        )

        return product

    @router.callback_query(F.data.startswith("admin_product:"))
    async def show_product(callback: CallbackQuery):
        product_id = int(callback.data.split(":")[1])

        await _render_product(callback, product_id)
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_toggle_product:"))
    async def toggle_product(callback: CallbackQuery):
        product_id = int(callback.data.split(":")[1])

        is_active = await CatalogAdminService.toggle_active(get_shop_id(), product_id)

        if is_active is None:
            await callback.answer("Товар не найден.", show_alert=True)
            return

        await _render_product(callback, product_id)
        await callback.answer("Показан покупателям" if is_active else "Скрыт от покупателей")

    @router.callback_query(F.data.startswith("admin_delete_product:"))
    async def confirm_delete_product(callback: CallbackQuery):
        product_id = int(callback.data.split(":")[1])

        await callback.message.edit_text(
            "Удалить товар вместе со всеми его вариантами? Это необратимо.",
            reply_markup=get_confirm_delete_keyboard(product_id)
        )

        await callback.answer()

    @router.callback_query(F.data.startswith("admin_delete_confirm:"))
    async def delete_product(callback: CallbackQuery):
        product_id = int(callback.data.split(":")[1])

        product = await CatalogAdminService.get_product(get_shop_id(), product_id)
        category_id = product["category_id"] if product else None

        await CatalogAdminService.delete_product(get_shop_id(), product_id)
        await callback.answer("Товар удалён")

        if category_id is not None:
            await _render_products(callback, category_id)
        else:
            await callback.message.edit_text(
                "⚙️ <b>Панель администратора</b>",
                reply_markup=get_admin_menu()
            )

    # ==========================
    # Мастер добавления товара
    # ==========================

    @router.callback_query(F.data.startswith("admin_add_product:"))
    async def start_add_product(callback: CallbackQuery, state: FSMContext):
        category_id = int(callback.data.split(":")[1])

        await state.set_state(AdminProductState.waiting_name)
        await state.update_data(category_id=category_id, variants=[])

        await callback.message.edit_text(
            "➕ <b>Новый товар</b>\n\nВведите название товара."
        )

        await callback.answer()

    @router.message(AdminProductState.waiting_name)
    async def process_name(message: Message, state: FSMContext):
        await state.update_data(name=message.text)
        await state.set_state(AdminProductState.waiting_description)

        await message.answer("Введите описание товара.")

    @router.message(AdminProductState.waiting_description)
    async def process_description(message: Message, state: FSMContext):
        await state.update_data(description=message.text)
        await state.set_state(AdminProductState.waiting_photos)
        await state.update_data(photos=[])

        prompt = await message.answer(
            "📸 <b>Фотографии товара</b>\n\n"
            "Отправьте одно или несколько фото.\n"
            "Когда закончите — нажмите «✅ Готово».",
            reply_markup=get_photos_done_keyboard()
        )
        await state.update_data(photo_prompt_id=prompt.message_id)

    @router.message(AdminProductState.waiting_photos, F.photo)
    async def collect_photo(message: Message, state: FSMContext):
        file_id = message.photo[-1].file_id

        try:
            await message.delete()
        except Exception:
            pass

        data = await state.get_data()
        photos = data.get("photos", [])
        photos.append(file_id)
        await state.update_data(photos=photos)

        prompt_id = data.get("photo_prompt_id")
        if prompt_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=prompt_id,
                    text=(
                        "📸 <b>Фотографии товара</b>\n\n"
                        f"Отправлено: <b>{len(photos)}</b> шт.\n"
                        "Можно отправить ещё или нажать «✅ Готово»."
                    ),
                    reply_markup=get_photos_done_keyboard()
                )
            except Exception:
                pass

    @router.callback_query(
        AdminProductState.waiting_photos,
        F.data == "admin_photos_done"
    )
    async def finish_photos(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        photo_count = len(data.get("photos", []))

        await state.set_state(AdminProductState.waiting_variant_volume)

        await callback.message.edit_text(
            f"📸 Сохранено фото: <b>{photo_count}</b> шт.\n\n"
            "Теперь добавим вариант товара (например, объём или размер).\n\n"
            "Укажите объём/размер (например: <i>200 г</i>)."
        )

        await callback.answer()

    @router.message(AdminProductState.waiting_variant_volume)
    async def process_variant_volume(message: Message, state: FSMContext):
        await state.update_data(current_volume=message.text)
        await state.set_state(AdminProductState.waiting_variant_price)

        await message.answer("Укажите цену в рублях (только число, например: <i>990</i>).")

    @router.message(AdminProductState.waiting_variant_price)
    async def process_variant_price(message: Message, state: FSMContext):
        price_text = message.text.strip().replace(" ", "")

        if not price_text.isdecimal():
            await message.answer("Цена должна быть числом. Попробуйте ещё раз, например: <i>990</i>.")
            return

        await state.update_data(current_price=int(price_text))
        await state.set_state(AdminProductState.waiting_variant_burn)

        await message.answer(
            "Время горения (для свечей), например <i>45 часов</i>.\n"
            "Если неприменимо — отправьте «-»."
        )

    @router.message(AdminProductState.waiting_variant_burn)
    async def process_variant_burn(message: Message, state: FSMContext):
        burn = None if message.text.strip() == "-" else message.text.strip()

        data = await state.get_data()

        variants = data.get("variants", [])
        variants.append({
            "volume": data["current_volume"],
            "price": data["current_price"],
            "burn": burn,
        })

        await state.update_data(variants=variants)
        await state.set_state(AdminProductState.confirm_more_variants)

        await message.answer(
            f"Добавлен вариант: {data['current_volume']} — {data['current_price']} ₽.\n\n"
            "Добавить ещё один вариант этого товара?",
            reply_markup=get_yes_no_keyboard(
                yes_data="admin_variant_more:yes",
                no_data="admin_variant_more:no",
            )
        )

    @router.callback_query(
        AdminProductState.confirm_more_variants,
        F.data == "admin_variant_more:yes"
    )
    async def add_another_variant(callback: CallbackQuery, state: FSMContext):
        await state.set_state(AdminProductState.waiting_variant_volume)

        await callback.message.edit_text("Укажите объём/размер следующего варианта.")
        await callback.answer()

    @router.callback_query(
        AdminProductState.confirm_more_variants,
        F.data == "admin_variant_more:no"
    )
    async def finish_add_product(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()

        product_id = await CatalogAdminService.create_product(get_shop_id(),
            category_id=data["category_id"],
            name=data["name"],
            description=data["description"],
            variants=data["variants"],
            photos=data.get("photos", []),
        )

        await state.clear()

        category_id = data["category_id"]
        products = await CatalogAdminService.get_products(get_shop_id(), category_id)

        await callback.message.edit_text(
            f"✅ Товар «{data['name']}» добавлен (ID {product_id}).\n\n"
            + _render_products_text(products),
            reply_markup=get_admin_products_keyboard(category_id, products)
        )

        await callback.answer()

    # ==========================
    # Редактирование товара
    # ==========================

    @router.callback_query(F.data.startswith("admin_edit:"))
    async def show_edit_menu(callback: CallbackQuery, state: FSMContext):
        product_id = int(callback.data.split(":")[1])

        await state.clear()

        product = await CatalogAdminService.get_product(get_shop_id(), product_id)

        if product is None:
            await callback.answer("Товар не найден.", show_alert=True)
            return

        await callback.message.edit_text(
            f"✏️ <b>Редактирование: {product['name']}</b>\n\n"
            "Выберите, что изменить:",
            reply_markup=get_admin_edit_keyboard(product_id)
        )

        await callback.answer()

    @router.callback_query(F.data.startswith("admin_edit_name:"))
    async def edit_name(callback: CallbackQuery, state: FSMContext):
        product_id = int(callback.data.split(":")[1])

        await state.set_state(AdminEditProductState.waiting_new_name)
        await state.update_data(product_id=product_id)

        await callback.message.edit_text("✏️ Введите новое название товара:")
        await callback.answer()

    @router.message(AdminEditProductState.waiting_new_name)
    async def process_new_name(message: Message, state: FSMContext):
        data = await state.get_data()
        product_id = data["product_id"]

        await CatalogAdminService.update_product(get_shop_id(), product_id, name=message.text)
        await state.clear()

        product = await CatalogAdminService.get_product(get_shop_id(), product_id)

        await message.answer(
            f"✅ Название изменено на «{message.text}».\n\n"
            + _render_product_text(product),
            reply_markup=get_admin_product_keyboard(product)
        )

    @router.callback_query(F.data.startswith("admin_edit_desc:"))
    async def edit_description(callback: CallbackQuery, state: FSMContext):
        product_id = int(callback.data.split(":")[1])

        await state.set_state(AdminEditProductState.waiting_new_description)
        await state.update_data(product_id=product_id)

        await callback.message.edit_text("✏️ Введите новое описание товара:")
        await callback.answer()

    @router.message(AdminEditProductState.waiting_new_description)
    async def process_new_description(message: Message, state: FSMContext):
        data = await state.get_data()
        product_id = data["product_id"]

        await CatalogAdminService.update_product(get_shop_id(), product_id, description=message.text)
        await state.clear()

        product = await CatalogAdminService.get_product(get_shop_id(), product_id)

        await message.answer(
            "✅ Описание обновлено.\n\n" + _render_product_text(product),
            reply_markup=get_admin_product_keyboard(product)
        )

    @router.callback_query(F.data.startswith("admin_edit_photos:"))
    async def edit_photos(callback: CallbackQuery, state: FSMContext):
        product_id = int(callback.data.split(":")[1])

        await state.clear()

        product = await CatalogAdminService.get_product(get_shop_id(), product_id)

        if product is None:
            await callback.answer("Товар не найден.", show_alert=True)
            return

        photo_count = len(product.get("photos", []))

        await callback.message.edit_text(
            f"📸 <b>Фотографии товара</b>\n\n"
            f"Текущее количество: {photo_count} шт.\n\n"
            "Удалить ненужное или добавить новое.",
            reply_markup=get_admin_photos_keyboard(product_id, product["photos"])
        )

        await callback.answer()

    @router.callback_query(F.data.startswith("admin_del_photo:"))
    async def delete_photo(callback: CallbackQuery):
        _, product_id, photo_id = callback.data.split(":")

        await CatalogAdminService.delete_photo(get_shop_id(), int(photo_id))

        product = await CatalogAdminService.get_product(get_shop_id(), int(product_id))

        photo_count = len(product.get("photos", [])) if product else 0

        await callback.message.edit_text(
            f"📸 <b>Фотографии товара</b>\n\n"
            f"Текущее количество: {photo_count} шт.\n\n"
            "Удалить ненужное или добавить новое.",
            reply_markup=get_admin_photos_keyboard(
                int(product_id),
                product["photos"] if product else [],
            )
        )

        await callback.answer("Фото удалено")

    @router.callback_query(F.data.startswith("admin_add_photo:"))
    async def add_photo_start(callback: CallbackQuery, state: FSMContext):
        product_id = int(callback.data.split(":")[1])

        await state.set_state(AdminEditProductState.waiting_add_photo)
        await state.update_data(product_id=product_id)

        await callback.message.edit_text(
            "📸 Отправьте фотографию товара."
        )

        await callback.answer()

    @router.message(AdminEditProductState.waiting_add_photo, F.photo)
    async def add_photo_process(message: Message, state: FSMContext):
        data = await state.get_data()
        product_id = data["product_id"]

        file_id = message.photo[-1].file_id

        await CatalogAdminService.add_photo(get_shop_id(), product_id, file_id)
        await state.clear()

        product = await CatalogAdminService.get_product(get_shop_id(), product_id)

        photo_count = len(product.get("photos", []))

        try:
            await message.delete()
        except Exception:
            pass

        await message.bot.send_message(
            chat_id=message.chat.id,
            text=(
                f"✅ Фото добавлено. Всего: {photo_count} шт.\n\n"
                "📸 <b>Фотографии товара</b>\n\n"
                "Удалить ненужное или добавить новое."
            ),
            reply_markup=get_admin_photos_keyboard(product_id, product["photos"])
        )

    return router
