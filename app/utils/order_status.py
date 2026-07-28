STATUS_LABELS = {
    "new": "🆕 Новый",
    "confirmed": "✅ Подтверждён",
    "paid": "💰 Оплачен",
    "shipped": "🚚 Отправлен",
    "done": "🏁 Выполнен",
    "cancelled": "❌ Отменён",
}

# Порядок последовательной смены статуса (без отмены).
STATUS_ORDER = ["new", "confirmed", "paid", "shipped", "done"]

NEXT_STATUS = {
    status: STATUS_ORDER[i + 1]
    for i, status in enumerate(STATUS_ORDER[:-1])
}
