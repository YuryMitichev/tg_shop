from app.core.enums import OrderStatus

STATUS_LABELS = {
    OrderStatus.NEW: "🆕 Новый",
    OrderStatus.CONFIRMED: "✅ Подтверждён",
    OrderStatus.PAID: "💰 Оплачен",
    OrderStatus.SHIPPED: "🚚 Отправлен",
    OrderStatus.DONE: "🏁 Выполнен",
    OrderStatus.CANCELLED: "❌ Отменён",
}

STATUS_NOTIFICATIONS = {
    OrderStatus.CONFIRMED: "✅ <b>Заказ №{order_id} подтверждён</b>\n\nМы свяжемся с вами для уточнения деталей.",
    OrderStatus.PAID: "💰 <b>Заказ №{order_id} оплачен</b>\n\nСпасибо! Собираем ваш заказ.",
    OrderStatus.SHIPPED: "🚚 <b>Заказ №{order_id} отправлен!</b>\n\nВ пути — скоро будет у вас.",
    OrderStatus.DONE: "🏁 <b>Заказ №{order_id} выполнен</b>\n\nСпасибо за покупку! Будем рады видеть вас снова. ❤️",
    OrderStatus.CANCELLED: "❌ <b>Заказ №{order_id} отменён</b>\n\nЕсли возникли вопросы — напишите нам.",
}

STATUS_ORDER = [
    OrderStatus.NEW,
    OrderStatus.CONFIRMED,
    OrderStatus.PAID,
    OrderStatus.SHIPPED,
    OrderStatus.DONE,
]

NEXT_STATUS = {
    status: STATUS_ORDER[i + 1]
    for i, status in enumerate(STATUS_ORDER[:-1])
}
