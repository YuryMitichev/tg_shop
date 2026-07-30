from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.utils.order_status import STATUS_LABELS, NEXT_STATUS


def get_admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="🗂 Товары", callback_data="admin_products")
    builder.button(text="📦 Заказы", callback_data="admin_orders")
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="💬 Сообщения", callback_data="admin_messages")
    builder.button(text="🎟 Промокоды", callback_data="admin_promos")

    builder.adjust(1)

    return builder.as_markup()


def get_admin_promos_keyboard(promos: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for p in promos:
        icon = "✅" if p["is_active"] else "🚫"
        if p["discount_type"] == "percent":
            val = f"−{p['discount_value']}%"
        else:
            val = f"−{p['discount_value']}₽"
        builder.button(
            text=f"{icon} {p['code']} — {val} ({p['used_count']}/{p['max_uses'] or '∞'})",
            callback_data=f"admin_promo:{p['id']}",
        )

    builder.button(text="➕ Создать промокод", callback_data="admin_promo_new")
    builder.button(text="⬅ Админ-меню", callback_data="admin_menu")

    builder.adjust(1)

    return builder.as_markup()


def get_admin_promo_detail_keyboard(promo_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if is_active:
        builder.button(text="🚫 Выключить", callback_data=f"admin_promo_toggle:{promo_id}")
    else:
        builder.button(text="✅ Включить", callback_data=f"admin_promo_toggle:{promo_id}")

    builder.button(text="🗑 Удалить", callback_data=f"admin_promo_delete:{promo_id}")
    builder.button(text="⬅ К промокодам", callback_data="admin_promos")

    builder.adjust(1)

    return builder.as_markup()


def get_admin_messages_keyboard(messages: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for msg in messages:
        mark = "📝" if not msg["is_default"] else "📄"
        builder.button(
            text=f"{mark} {msg['label']}",
            callback_data=f"admin_msg:{msg['key']}",
        )

    builder.adjust(1)

    builder.button(text="⬅ Админ-меню", callback_data="admin_menu")

    builder.adjust(1)

    return builder.as_markup()


def get_admin_message_edit_keyboard(key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="🔄 Сбросить к стандарту", callback_data=f"admin_msg_reset:{key}")
    builder.button(text="⬅ К сообщениям", callback_data="admin_messages")

    builder.adjust(1)

    return builder.as_markup()


def _cat_label(category: dict) -> str:
    emoji = category.get("emoji")
    return f"{emoji} {category['name']}" if emoji else category["name"]


def get_admin_categories_keyboard(categories: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for category in categories:
        builder.button(
            text=_cat_label(category),
            callback_data=f"admin_cat:{category['id']}"
        )

    builder.adjust(1)

    builder.button(text="⚙️ Управление категориями", callback_data="admin_manage_categories")

    builder.button(text="⬅ Админ-меню", callback_data="admin_menu")

    builder.adjust(1)

    return builder.as_markup()


def get_admin_manage_categories_keyboard(categories: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for category in categories:
        builder.button(
            text=f"✏️ {_cat_label(category)}",
            callback_data=f"admin_rename_cat:{category['id']}"
        )

    builder.adjust(1)

    builder.button(text="➕ Добавить категорию", callback_data="admin_add_category")

    builder.button(text="⬅ К категориям", callback_data="admin_products")

    builder.adjust(1)

    return builder.as_markup()


def get_admin_rename_category_keyboard(category_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="😀 Сменить эмодзи", callback_data=f"admin_emoji_cat:{category_id}")
    builder.button(text="🗑 Удалить категорию", callback_data=f"admin_delete_cat:{category_id}")
    builder.button(text="⬅ Назад", callback_data="admin_manage_categories")

    builder.adjust(1)

    return builder.as_markup()


def get_confirm_delete_category_keyboard(category_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="❌ Да, удалить", callback_data=f"admin_delete_cat_confirm:{category_id}")
    builder.button(text="Отмена", callback_data=f"admin_rename_cat:{category_id}")

    builder.adjust(1)

    return builder.as_markup()


def get_admin_products_keyboard(category_id: int, products: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for product in products:
        mark = "👁" if product["is_active"] else "🙈"

        builder.button(
            text=f"{mark} {product['name']}",
            callback_data=f"admin_product:{product['id']}"
        )

    builder.adjust(1)

    builder.button(text="➕ Добавить товар", callback_data=f"admin_add_product:{category_id}")

    builder.adjust(1)

    builder.button(text="⬅ Категории", callback_data="admin_products")

    builder.adjust(1)

    return builder.as_markup()


def get_admin_product_keyboard(product: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    toggle_text = "🙈 Скрыть" if product["is_active"] else "👁 Показать"

    builder.button(text="✏️ Редактировать", callback_data=f"admin_edit:{product['id']}")
    builder.button(text=toggle_text, callback_data=f"admin_toggle_product:{product['id']}")
    builder.button(text="🗑 Удалить", callback_data=f"admin_delete_product:{product['id']}")

    builder.adjust(1)

    builder.button(text="⬅ К товарам", callback_data=f"admin_cat:{product['category_id']}")

    builder.adjust(1)

    return builder.as_markup()


def get_admin_edit_keyboard(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="✏️ Название", callback_data=f"admin_edit_name:{product_id}")
    builder.button(text="✏️ Описание", callback_data=f"admin_edit_desc:{product_id}")
    builder.button(text="📸 Фотографии", callback_data=f"admin_edit_photos:{product_id}")

    builder.adjust(1)

    builder.button(text="⬅ К товару", callback_data=f"admin_product:{product_id}")

    builder.adjust(1)

    return builder.as_markup()


def get_admin_photos_keyboard(product_id: int, photos: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for i, photo in enumerate(photos, 1):
        builder.button(
            text=f"🗑 Фото {i}",
            callback_data=f"admin_del_photo:{product_id}:{photo['id']}",
        )

    if photos:
        builder.adjust(3)

    builder.button(text="➕ Добавить фото", callback_data=f"admin_add_photo:{product_id}")

    builder.button(text="⬅ Назад", callback_data=f"admin_edit:{product_id}")

    builder.adjust(1)

    return builder.as_markup()


def get_photos_done_keyboard(done_data: str = "admin_photos_done") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="✅ Готово", callback_data=done_data)

    builder.adjust(1)

    return builder.as_markup()


def get_confirm_delete_keyboard(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="❌ Да, удалить", callback_data=f"admin_delete_confirm:{product_id}")
    builder.button(text="Отмена", callback_data=f"admin_product:{product_id}")

    builder.adjust(1)

    return builder.as_markup()


def get_yes_no_keyboard(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="➕ Ещё вариант", callback_data=yes_data)
    builder.button(text="✅ Готово", callback_data=no_data)

    builder.adjust(2)

    return builder.as_markup()


def get_admin_orders_keyboard(orders: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for order in orders:
        label = STATUS_LABELS.get(order["status"], order["status"])

        builder.button(
            text=f"№{order['id']} — {label} — {order['total_amount']} ₽",
            callback_data=f"admin_order:{order['id']}"
        )

    builder.adjust(1)

    builder.button(text="⬅ Админ-меню", callback_data="admin_menu")

    builder.adjust(1)

    return builder.as_markup()


def get_admin_order_keyboard(order_id: int, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    next_status = NEXT_STATUS.get(status)

    if next_status:
        builder.button(
            text=f"➡ {STATUS_LABELS[next_status]}",
            callback_data=f"admin_order_status:{order_id}:{next_status}"
        )
        builder.adjust(1)

    if status not in ("done", "cancelled"):
        builder.button(text="❌ Отменить заказ", callback_data=f"admin_order_status:{order_id}:cancelled")
        builder.adjust(1)

    builder.button(text="⬅ К заказам", callback_data="admin_orders")

    builder.adjust(1)

    return builder.as_markup()
