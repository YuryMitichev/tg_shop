import base64
import logging

from sqlalchemy import select

from app.database.db import async_session
from app.models.order import Order
from app.services.tinkoff_client import TinkoffClient, verify_token
from app.core.config import settings

logger = logging.getLogger(__name__)


class PaymentService:
    """
    Связывает заказы с платёжной системой Тинькофф.
    """

    @staticmethod
    def _notification_url() -> str:
        return f"{settings.app_base_url}/payments/tinkoff/webhook"

    @staticmethod
    async def create_payment(order_id: int, amount: int, description: str) -> dict | None:
        """
        Создаёт платёж и получает QR-код.

        Возвращает dict:
        - payment_id: str
        - qr_base64: str (PNG в base64)
        - payment_url: str

        При ошибке возвращает None.
        """
        result = await TinkoffClient.init_payment(
            order_id=order_id,
            amount_rub=amount,
            description=description,
            notification_url=PaymentService._notification_url(),
        )

        if result is None:
            return None

        payment_id = str(result["PaymentId"])

        await PaymentService._save_payment_id(order_id, payment_id)

        qr = await TinkoffClient.get_qr(payment_id)

        if qr is None:
            return None

        return {
            "payment_id": payment_id,
            "qr_base64": qr.get("QrCode"),
            "payment_url": qr.get("PaymentUrl"),
        }

    @staticmethod
    async def _save_payment_id(order_id: int, payment_id: str) -> None:
        async with async_session() as session:
            order = await session.get(Order, order_id)
            if order:
                order.payment_id = payment_id
                await session.commit()

    @staticmethod
    async def process_notification(data: dict) -> bool:
        """
        Обрабатывает вебхук от Тинькофф.

        Возвращает True если заказ найден и статус обработан.
        """
        if not verify_token(data, settings.tinkoff_password):
            logger.warning("Tinkoff webhook: неверный токен")
            return False

        order_id_str = data.get("OrderId")
        status = data.get("Status")

        if not order_id_str:
            return False

        try:
            order_id = int(order_id_str)
        except (TypeError, ValueError):
            return False

        async with async_session() as session:
            order = await session.get(Order, order_id)

            if not order:
                logger.warning("Tinkoff webhook: заказ %s не найден", order_id)
                return False

            if status == "CONFIRMED":
                if order.status not in ("paid", "done", "cancelled"):
                    order.status = "paid"
                    await session.commit()
                    logger.info("Заказ %s оплачен", order_id)
                    return "paid"

            elif status in ("REJECTED", "CANCELED"):
                logger.info("Платеж заказа %s отклонён: %s", order_id, status)

        return True

    @staticmethod
    async def get_order_with_user(order_id: int) -> dict | None:
        """Возвращает заказ с telegram_user_id для уведомлений."""
        async with async_session() as session:
            order = await session.get(Order, order_id)

            if not order:
                return None

            return {
                "id": order.id,
                "telegram_user_id": order.telegram_user_id,
                "status": order.status,
                "total_amount": order.total_amount,
            }
