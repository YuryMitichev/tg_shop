STATUS_LABELS = {
    "new": "🆕 Новый",
    "confirmed": "✅ Подтверждён",
    "paid": "💰 Оплачен",
    "shipped": "🚚 Отправлен",
    "done": "🏁 Выполнен",
    "cancelled": "❌ Отменён",
}

STATUS_NOTIFICATIONS = {
    "confirmed": "✅ <b>Заказ №{order_id} подтверждён</b>\n\nМы свяжемся с вами для уточнения деталей.",
    "paid": "💰 <b>Заказ №{order_id} оплачен</b>\n\nСпасибо! Собираем ваш заказ.",
    "shipped": "🚚 <b>Заказ №{order_id} отправлен!</b>\n\nВ пути — скоро будет у вас.",
    "done": "🏁 <b>Заказ №{order_id} выполнен</b>\n\nСпасибо за покупку! Будем рады видеть вас снова. ❤️",
    "cancelled": "❌ <b>Заказ №{order_id} отменён</b>\n\nЕсли возникли вопросы — напишите нам.",
}

# Порядок последовательной смены статуса (без отмены).
STATUS_ORDER = ["new", "confirmed", "paid", "shipped", "done"]

NEXT_STATUS = {
    status: STATUS_ORDER[i + 1]
    for i, status in enumerate(STATUS_ORDER[:-1])
}
