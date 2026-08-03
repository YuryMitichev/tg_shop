import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services.order_payment_service import OrderPaymentService
from app.services.payment_service import PaymentService
from app.services.subscription_payment_service import SubscriptionPaymentService
from app.services.yookassa_client import YooKassaClient

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


@router.post("/yookassa/webhook")
async def yookassa_webhook(request: Request):
    """
    Вебхук для уведомлений от ЮKassa.

    Перед обработкой каждый платёж верифицируется через API ЮKassa
    (GET /payments/{id}) — это исключает поддельные запросы.

    Маршрутизация по metadata.type:
    - "order" → оплата заказа (OrderPaymentService)
    - "subscription" / отсутствует → оплата подписки (SubscriptionPaymentService)
    """
    if not settings.yookassa_enabled:
        return JSONResponse(
            status_code=403,
            content={"error": "yookassa_not_configured"},
        )

    data = await request.json()

    payment_id = data.get("object", {}).get("id")
    event = data.get("event")

    logger.info("ЮKassa webhook: event=%s, payment_id=%s", event, payment_id)

    if not payment_id:
        logger.warning("ЮKassa webhook: нет payment_id в payload")
        return JSONResponse(
            status_code=400,
            content={"error": "missing_payment_id"},
        )

    verified = await YooKassaClient.get_payment(payment_id)

    if verified is None:
        logger.error("ЮKassa webhook: не удалось верифицировать платёж %s", payment_id)
        return JSONResponse(
            status_code=400,
            content={"error": "verification_failed"},
        )

    if verified.get("status") != "succeeded":
        logger.info(
            "ЮKassa webhook: платёж %s статус %s — пропускаю",
            payment_id,
            verified.get("status"),
        )
        return JSONResponse(content={"status": "ok"})

    verified_data = {"event": event, "object": verified}

    metadata = verified.get("metadata", {})
    ptype = metadata.get("type", "subscription")

    if ptype == "order":
        await OrderPaymentService.process_webhook(verified_data)
    else:
        await SubscriptionPaymentService.process_webhook(verified_data)

    return JSONResponse(content={"status": "ok"})


async def _notify_user_paid(data: dict) -> None:
    """Уведомление пользователя и админа об оплате."""
    from app.bot.bot import get_bot

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

    bot = get_bot(order["shop_id"])
    if bot is None:
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
