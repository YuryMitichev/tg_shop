from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.bot.filters.admin import IsAdmin
from app.bot.keyboards.admin import (
    get_admin_order_keyboard,
    get_admin_orders_keyboard,
)
from app.bot.shop_context import get_shop_id
from app.services.order_admin_service import OrderAdminService
from app.services.order_service import OrderService
from app.utils.escape import esc
from app.utils.order_status import STATUS_LABELS, STATUS_NOTIFICATIONS


def setup_orders_router() -> Router:
    router = Router()
    router.message.filter(IsAdmin())
    router.callback_query.filter(IsAdmin())

    @router.callback_query(F.data == "admin_orders")
    async def show_orders(callback: CallbackQuery):
        orders = await OrderAdminService.get_orders(get_shop_id(), limit=15)

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
        order = await OrderAdminService.get_order(get_shop_id(), order_id)

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

        await OrderAdminService.set_order_status(get_shop_id(), int(order_id), new_status)
        await callback.answer(f"Статус изменён: {STATUS_LABELS[new_status]}")

        notification = STATUS_NOTIFICATIONS.get(new_status)
        if notification:
            user_id = await OrderService.get_order_owner(get_shop_id(), int(order_id))
            if user_id:
                try:
                    await callback.bot.send_message(
                        chat_id=user_id,
                        text=notification.format(order_id=order_id),
                    )
                except Exception:
                    pass

        await _render_order(callback, int(order_id))

    return router
