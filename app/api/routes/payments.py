import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services.payment_service import PaymentService

router = APIRouter()

logger = logging.getLogger(__name__)


@router.post("/tinkoff/webhook")
async def tinkoff_webhook(request: Request):
    """
    Вебхук для уведомлений от Тинькофф.

    Тинькофф присылает POST с данными платежа.
    Подтверждаем приём ответом 200 OK.
    """
    data = await request.json()

    logger.info("Tinkoff webhook: %s", data.get("Status"))

    result = await PaymentService.process_notification(data)

    if result == "paid":
        await _notify_user_paid(data)

    return JSONResponse(content={"status": "ok"})


async def _notify_user_paid(data: dict) -> None:
    """Уведомление пользователя и админа об оплате."""
    from app.bot.bot import get_bot

    bot = get_bot()
    if bot is None:
        return

    order_id_str = data.get("OrderId")
    if not order_id_str:
        return

    try:
        order_id = int(order_id_str)
    except (TypeError, ValueError):
        return

    order = await PaymentService.get_order_with_user(order_id)
    if not order:
        return

    try:
        await bot.send_message(
            order["telegram_user_id"],
            f"✅ <b>Оплата получена!</b>\n\n"
            f"Заказ №{order['id']} на сумму <b>{order['total_amount']} ₽</b> оплачен.\n"
            "Мы свяжемся с вами для подтверждения доставки.",
        )
    except Exception as e:
        logger.error("Не удалось уведомить пользователя: %s", e)
