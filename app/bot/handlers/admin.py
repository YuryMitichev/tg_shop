from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.filters.admin import IsAdmin
from app.bot.states.admin_product import (
    AdminProductState,
    AdminEditProductState,
    AdminCategoryState,
    AdminMessageState,
    AdminPromoState,
)
from app.bot.keyboards.admin import (
    get_admin_menu,
    get_admin_categories_keyboard,
    get_admin_products_keyboard,
    get_admin_product_keyboard,
    get_confirm_delete_keyboard,
    get_yes_no_keyboard,
    get_admin_orders_keyboard,
    get_admin_order_keyboard,
    get_admin_edit_keyboard,
    get_admin_photos_keyboard,
    get_photos_done_keyboard,
    get_admin_manage_categories_keyboard,
    get_admin_rename_category_keyboard,
    get_confirm_delete_category_keyboard,
    get_admin_messages_keyboard,
    get_admin_message_edit_keyboard,
    get_admin_promos_keyboard,
    get_admin_promo_detail_keyboard,
)
from app.services.admin_service import AdminService
from app.services.message_service import MessageService
from app.services.order_service import OrderService
from app.services.promo_service import PromoCodeService
from app.utils.order_status import STATUS_LABELS, STATUS_NOTIFICATIONS
from app.utils.escape import esc

router = Router()

# Все хендлеры этого роутера доступны только администратору.
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# ==========================
# Главное меню админки
# ==========================

@router.message(Command("admin"))
async def open_admin_menu(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "⚙️ <b>Панель администратора</b>",
        reply_markup=get_admin_menu()
    )


@router.callback_query(F.data == "admin_menu")
async def admin_menu_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    await callback.message.edit_text(
        "⚙️ <b>Панель администратора</b>",
        reply_markup=get_admin_menu()
    )

    await callback.answer()


# ==========================
# Статистика
# ==========================

@router.callback_query(F.data == "admin_stats")
async def show_stats(callback: CallbackQuery):
    stats = await AdminService.get_stats()

    lines = [
        "📊 <b>Статистика магазина</b>\n",
        f"📦 Всего заказов: <b>{stats['total_orders']}</b>",
        f"🆕 Новых: <b>{stats['new_orders']}</b>",
        f"❌ Отменено: <b>{stats['cancelled_orders']}</b>",
        "",
        f"💰 Выручка за всё время: <b>{stats['total_revenue']} ₽</b>",
        f"📅 За текущий месяц: <b>{stats['month_revenue']} ₽</b>",
    ]

    if stats["top_products"]:
        lines.append("\n🏆 <b>Топ-5 товаров по выручке:</b>")
        for i, product in enumerate(stats["top_products"], 1):
            lines.append(
                f"{i}. {product['name']} — {product['quantity']} шт. / {product['revenue']} ₽"
            )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=get_admin_menu()
    )

    await callback.answer()


# ==========================
# Управление категориями
# ==========================

@router.callback_query(F.data == "admin_manage_categories")
async def manage_categories(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    categories = await AdminService.get_categories()

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
        await AdminService.update_category_emoji(category_id, emoji)
        await state.clear()

        categories = await AdminService.get_categories()
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
        category_id = await AdminService.create_category(name, emoji)
        await state.clear()

        categories = await AdminService.get_categories()

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

    categories = await AdminService.get_categories()
    category = next((c for c in categories if c["id"] == category_id), None)

    if category is None:
        await callback.answer("Категория не найдена.", show_alert=True)
        return

    count = await AdminService.count_products_in_category(category_id)

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

    await AdminService.rename_category(category_id, name)
    await state.clear()

    categories = await AdminService.get_categories()

    await message.answer(
        f"✅ Категория переименована в «{name}».\n\n"
        "🗂 <b>Управление категориями</b>\n\n"
        "Нажмите на категорию, чтобы переименовать или удалить.",
        reply_markup=get_admin_manage_categories_keyboard(categories)
    )


@router.callback_query(F.data.startswith("admin_delete_cat:"))
async def delete_category_confirm(callback: CallbackQuery):
    category_id = int(callback.data.split(":")[1])

    count = await AdminService.count_products_in_category(category_id)

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

    await AdminService.delete_category(category_id)

    categories = await AdminService.get_categories()

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
    categories = await AdminService.get_categories()

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
    products = await AdminService.get_products(category_id)

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
    product = await AdminService.get_product(product_id)

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

    is_active = await AdminService.toggle_active(product_id)

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

    product = await AdminService.get_product(product_id)
    category_id = product["category_id"] if product else None

    await AdminService.delete_product(product_id)
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

    product_id = await AdminService.create_product(
        category_id=data["category_id"],
        name=data["name"],
        description=data["description"],
        variants=data["variants"],
        photos=data.get("photos", []),
    )

    await state.clear()

    category_id = data["category_id"]
    products = await AdminService.get_products(category_id)

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

    product = await AdminService.get_product(product_id)

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

    await AdminService.update_product(product_id, name=message.text)
    await state.clear()

    product = await AdminService.get_product(product_id)

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

    await AdminService.update_product(product_id, description=message.text)
    await state.clear()

    product = await AdminService.get_product(product_id)

    await message.answer(
        "✅ Описание обновлено.\n\n" + _render_product_text(product),
        reply_markup=get_admin_product_keyboard(product)
    )


@router.callback_query(F.data.startswith("admin_edit_photos:"))
async def edit_photos(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split(":")[1])

    await state.clear()

    product = await AdminService.get_product(product_id)

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

    await AdminService.delete_photo(int(photo_id))

    product = await AdminService.get_product(int(product_id))

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

    await AdminService.add_photo(product_id, file_id)
    await state.clear()

    product = await AdminService.get_product(product_id)

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


# ==========================
# Заказы
# ==========================

@router.callback_query(F.data == "admin_orders")
async def show_orders(callback: CallbackQuery):
    orders = await AdminService.get_orders(limit=15)

    await callback.message.edit_text(
        "📦 <b>Последние заказы</b>" if orders else "Заказов пока нет.",
        reply_markup=get_admin_orders_keyboard(orders)
    )

    await callback.answer()


def _render_order_text(order: dict) -> str:
    lines = [
        f"📦 <b>Заказ №{order['id']}</b>\n",
        f"Статус: {STATUS_LABELS.get(order['status'], order['status'])}\n",
        f"👤 {esc(order['full_name'])}",
        f"📞 {esc(order['phone'])}",
        f"📍 {esc(order['address'])}\n",
    ]

    for item in order["items"]:
        lines.append(
            f"• {item['product_name']} ({item['variant_volume']}) "
            f"× {item['quantity']} — {item['price'] * item['quantity']} ₽"
        )

    lines.append(f"\n💰 Итого: <b>{order['total_amount']} ₽</b>")

    return "\n".join(lines)


async def _render_order(callback: CallbackQuery, order_id: int) -> None:
    order = await AdminService.get_order(order_id)

    if order is None:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    await callback.message.edit_text(
        _render_order_text(order),
        reply_markup=get_admin_order_keyboard(order["id"], order["status"])
    )


@router.callback_query(F.data.startswith("admin_order:"))
async def show_order(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])

    await _render_order(callback, order_id)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_order_status:"))
async def change_order_status(callback: CallbackQuery):
    _, order_id, new_status = callback.data.split(":")

    if new_status not in STATUS_LABELS:
        await callback.answer("Неизвестный статус.", show_alert=True)
        return

    await AdminService.set_order_status(int(order_id), new_status)
    await callback.answer(f"Статус изменён: {STATUS_LABELS[new_status]}")

    notification = STATUS_NOTIFICATIONS.get(new_status)
    if notification:
        user_id = await OrderService.get_order_owner(int(order_id))
        if user_id:
            try:
                await callback.bot.send_message(
                    chat_id=user_id,
                    text=notification.format(order_id=order_id),
                )
            except Exception:
                pass

    await _render_order(callback, int(order_id))


# ==========================
# Системные сообщения
# ==========================

@router.callback_query(F.data == "admin_messages")
async def list_messages(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    messages = await MessageService.get_all()

    await callback.message.edit_text(
        "💬 <b>Системные сообщения</b>\n\n"
        "📄 — стандартный текст\n"
        "📝 — изменённый текст\n\n"
        "Выберите сообщение для редактирования:",
        reply_markup=get_admin_messages_keyboard(messages),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("admin_msg:"))
async def edit_message_start(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]

    msg = await MessageService.get_one(key)

    if msg is None:
        await callback.answer("Сообщение не найдено.", show_alert=True)
        return

    await state.set_state(AdminMessageState.waiting_new_content)
    await state.update_data(msg_key=key)

    status = "стандартный" if msg["is_default"] else "изменённый"

    await callback.message.edit_text(
        f"✏️ <b>{msg['label']}</b>\n"
        f"Статус: {status}\n\n"
        f"Текущий текст:\n\n{msg['content']}\n\n"
        "Отправьте новый текст сообщения.\n"
        "Поддерживаются HTML-теги: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, <code>&lt;code&gt;</code>.",
        reply_markup=get_admin_message_edit_keyboard(key),
    )

    await callback.answer()


@router.message(AdminMessageState.waiting_new_content)
async def edit_message_save(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data["msg_key"]

    await MessageService.update(key, message.text)
    await state.clear()

    messages = await MessageService.get_all()

    await message.answer(
        "✅ Текст сообщения обновлён.\n\n"
        "💬 <b>Системные сообщения</b>\n\n"
        "📄 — стандартный текст\n"
        "📝 — изменённый текст\n\n"
        "Выберите сообщение для редактирования:",
        reply_markup=get_admin_messages_keyboard(messages),
    )


@router.callback_query(F.data.startswith("admin_msg_reset:"))
async def reset_message(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]

    await MessageService.reset(key)
    await state.clear()

    msg = await MessageService.get_one(key)

    if msg is None:
        await callback.answer("Сообщение не найдено.", show_alert=True)
        return

    messages = await MessageService.get_all()

    await callback.message.edit_text(
        f"✅ Сброшено к стандарту: <b>{msg['label']}</b>\n\n"
        "💬 <b>Системные сообщения</b>\n\n"
        "📄 — стандартный текст\n"
        "📝 — изменённый текст\n\n"
        "Выберите сообщение для редактирования:",
        reply_markup=get_admin_messages_keyboard(messages),
    )

    await callback.answer("Сброшено к стандарту")


# ==========================
# Промокоды
# ==========================

@router.callback_query(F.data == "admin_promos")
async def list_promos(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    promos = await PromoCodeService.get_all()

    await callback.message.edit_text(
        "🎟 <b>Промокоды</b>\n\n"
        "✅ — активен, 🚫 — выключен",
        reply_markup=get_admin_promos_keyboard(promos),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("admin_promo:"))
async def show_promo_detail(callback: CallbackQuery):
    promo_id = int(callback.data.split(":")[1])

    promos = await PromoCodeService.get_all()
    promo = next((p for p in promos if p["id"] == promo_id), None)

    if promo is None:
        await callback.answer("Промокод не найден.", show_alert=True)
        return

    if promo["discount_type"] == "percent":
        val = f"−{promo['discount_value']}%"
    else:
        val = f"−{promo['discount_value']} ₽"

    uses = f"{promo['used_count']}/{promo['max_uses']}" if promo["max_uses"] else f"{promo['used_count']}/∞"
    status = "✅ Активен" if promo["is_active"] else "🚫 Выключен"

    await callback.message.edit_text(
        f"🎟 <b>Промокод {promo['code']}</b>\n\n"
        f"Скидка: {val}\n"
        f"Использовано: {uses}\n"
        f"Статус: {status}",
        reply_markup=get_admin_promo_detail_keyboard(promo_id, promo["is_active"]),
    )

    await callback.answer()


@router.callback_query(F.data == "admin_promo_new")
async def create_promo_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminPromoState.waiting_code)

    await callback.message.edit_text(
        "🎟 <b>Создание промокода</b>\n\n"
        "Шаг 1/4: введите код промокода (например: <code>NEW10</code>):",
    )

    await callback.answer()


@router.message(AdminPromoState.waiting_code)
async def create_promo_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()

    if len(code) < 3 or len(code) > 20:
        await message.answer("Код должен быть 3–20 символов. Попробуйте ещё раз.")
        return

    await state.update_data(code=code)
    await state.set_state(AdminPromoState.waiting_type)

    builder = InlineKeyboardBuilder()
    builder.button(text="Процент (%)", callback_data="promo_type:percent")
    builder.button(text="Фиксированная сумма (₽)", callback_data="promo_type:fixed")
    builder.adjust(1)

    await message.answer(
        "Шаг 2/4: выберите тип скидки:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("promo_type:"), AdminPromoState.waiting_type)
async def create_promo_type(callback: CallbackQuery, state: FSMContext):
    discount_type = callback.data.split(":")[1]

    await state.update_data(discount_type=discount_type)
    await state.set_state(AdminPromoState.waiting_value)

    unit = "%" if discount_type == "percent" else " ₽"
    await callback.message.edit_text(
        f"Шаг 3/4: введите размер скидки в {unit}:\n"
        "(для процента — число от 1 до 100)",
    )

    await callback.answer()


@router.message(AdminPromoState.waiting_value)
async def create_promo_value(message: Message, state: FSMContext):
    text = message.text.strip()

    if not text.isdigit():
        await message.answer("Введите число.")
        return

    value = int(text)

    data = await state.get_data()

    if data["discount_type"] == "percent" and (value < 1 or value > 100):
        await message.answer("Проент должен быть от 1 до 100. Попробуйте ещё раз.")
        return

    if value < 1:
        await message.answer("Сумма должна быть больше 0. Попробуйте ещё раз.")
        return

    await state.update_data(discount_value=value)
    await state.set_state(AdminPromoState.waiting_max_uses)

    builder = InlineKeyboardBuilder()
    builder.button(text="♾ Без лимита", callback_data="promo_uses:unlimited")

    await message.answer(
        "Шаг 4/4: введите максимальное количество использований,\n"
        "или нажмите «Без лимита»:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "promo_uses:unlimited", AdminPromoState.waiting_max_uses)
async def create_promo_unlimited(callback: CallbackQuery, state: FSMContext):
    await _finish_promo_creation(callback, state, max_uses=None)


@router.message(AdminPromoState.waiting_max_uses)
async def create_promo_max_uses(message: Message, state: FSMContext):
    text = message.text.strip()

    if not text.isdigit():
        await message.answer("Введите число.")
        return

    await _finish_promo_creation(message, state, max_uses=int(text))


async def _finish_promo_creation(event, state: FSMContext, max_uses: int | None):
    data = await state.get_data()
    await state.clear()

    promo_id = await PromoCodeService.create(
        code=data["code"],
        discount_type=data["discount_type"],
        discount_value=data["discount_value"],
        max_uses=max_uses,
    )

    unit = "%" if data["discount_type"] == "percent" else " ₽"
    uses_str = str(max_uses) if max_uses else "∞"

    promos = await PromoCodeService.get_all()

    msg = event.message if isinstance(event, CallbackQuery) else event

    await msg.answer(
        f"✅ Промокод <b>{data['code']}</b> создан!\n\n"
        f"Скидка: −{data['discount_value']}{unit}\n"
        f"Лимит: {uses_str} использований",
        reply_markup=get_admin_promos_keyboard(promos),
    )


@router.callback_query(F.data.startswith("admin_promo_toggle:"))
async def toggle_promo(callback: CallbackQuery):
    promo_id = int(callback.data.split(":")[1])

    await PromoCodeService.toggle_active(promo_id)

    promos = await PromoCodeService.get_all()

    await callback.message.edit_text(
        "🎟 <b>Промокоды</b>\n\n"
        "✅ — активен, 🚫 — выключен",
        reply_markup=get_admin_promos_keyboard(promos),
    )

    await callback.answer("Статус изменён")


@router.callback_query(F.data.startswith("admin_promo_delete:"))
async def delete_promo(callback: CallbackQuery):
    promo_id = int(callback.data.split(":")[1])

    await PromoCodeService.delete(promo_id)

    promos = await PromoCodeService.get_all()

    await callback.message.edit_text(
        "✅ Промокод удалён.\n\n"
        "🎟 <b>Промокоды</b>\n\n"
        "✅ — активен, 🚫 — выключен",
        reply_markup=get_admin_promos_keyboard(promos),
    )

    await callback.answer("Удалён")
