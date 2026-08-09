from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.filters.admin import IsAdmin
from app.bot.filters.subscription import SubscriptionActive
from app.bot.keyboards.admin import get_admin_menu
from app.bot.shop_context import get_shop_id
from app.core.config import settings
from app.services.stats_service import StatsService

from .catalog import setup_catalog_router
from .messages import setup_messages_router
from .orders import setup_orders_router
from .promos import setup_promos_router


def _admin_panel_link_kb() -> InlineKeyboardMarkup | None:
    admin_url = settings.admin_panel_url
    if not admin_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Открыть админ-панель", url=f"{admin_url}/login")]
        ]
    )


def setup_router() -> Router:
    router = Router()

    router.message.filter(IsAdmin())
    router.callback_query.filter(IsAdmin())

    # ==========================
    # Главное меню админки
    # ==========================

    @router.message(Command("admin"))
    async def open_admin_menu(message: Message, state: FSMContext):
        await state.clear()

        await message.answer(
            "⚙️ <b>Панель администратора</b>\n\n"
            "Управляйте товарами, заказами, промокодами и статистикой "
            "в удобной веб-админ-панели 👇",
            reply_markup=_admin_panel_link_kb(),
        )

    @router.callback_query(F.data == "admin_menu")
    async def admin_menu_callback(callback: CallbackQuery, state: FSMContext):
        await state.clear()

        await callback.message.edit_text(
            "⚙️ <b>Панель администратора</b>\n\n"
            "Управляйте товарами, заказами, промокодами и статистикой "
            "в удобной веб-админ-панели 👇",
            reply_markup=_admin_panel_link_kb(),
        )

        await callback.answer()

    # ==========================
    # Статистика
    # ==========================

    @router.callback_query(F.data == "admin_stats", SubscriptionActive())
    async def show_stats(callback: CallbackQuery):
        stats = await StatsService.get_stats(get_shop_id())

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
    # Под-роутеры
    # ==========================

    router.include_router(setup_catalog_router())
    router.include_router(setup_orders_router())
    router.include_router(setup_messages_router())
    router.include_router(setup_promos_router())

    return router
