import logging
from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.core.enums import OrderStatus
from app.database.db import async_session
from app.models.order import Order
from app.services.shop_service import ShopService
from app.services.yookassa_client import YooKassaClient

logger = logging.getLogger(__name__)


class OrderPaymentService:
    """Создаёт платежи ЮKassa для заказов и обрабатывает вебхуки."""

    @staticmethod
    async def create_payment(shop_id: int, order_id: int) -> dict | None:
        """
        Создаёт платёж ЮKassa для заказа.

        Возвращает dict:
        - payment_id: str
        - confirmation_url: str

        При ошибке возвращает None.
        """
        async with async_session() as session:
            order = await session.get(Order, order_id)
            if order is None or order.shop_id != shop_id:
                return None

            amount = order.total_amount
            description = f"Заказ №{order_id}"

        return_url = settings.webapp_url or settings.admin_panel_url or "https://t.me"

        creds = await ShopService.get_yookassa_credentials(shop_id)
        if creds is None:
            logger.error("ЮKassa ключи не настроены для магазина %d", shop_id)
            return None

        result = await YooKassaClient.create_payment(
            amount_rub=float(amount),
            description=description,
            return_url=return_url,
            metadata={
                "type": "order",
                "shop_id": str(shop_id),
                "order_id": str(order_id),
            },
            shop_id=creds[0],
            secret_key=creds[1],
        )

        if result is None:
            logger.error("Не удалось создать платёж для заказа %d", order_id)
            return None

        await OrderPaymentService._save_payment_id(order_id, result["payment_id"])

        return result

    @staticmethod
    async def _save_payment_id(order_id: int, payment_id: str) -> None:
        async with async_session() as session:
            order = await session.get(Order, order_id)
            if order:
                order.payment_id = payment_id
                await session.commit()

    @staticmethod
    async def process_webhook(data: dict) -> bool:
        """
        Обрабатывает вебхук ЮKassa для заказа.

        Ожидает metadata.type == "order".
        """
        event = data.get("event")
        obj = data.get("object")

        if not event or not obj:
            return False

        metadata = obj.get("metadata", {})
        payment_id = obj.get("id")

        try:
            order_id = int(metadata.get("order_id", 0))
            shop_id = int(metadata.get("shop_id", 0))
        except (TypeError, ValueError):
            return False

        if not order_id:
            return False

        if event == "payment.succeeded":
            async with async_session() as session:
                order = await session.get(Order, order_id)
                if order is None:
                    logger.warning("ЮKassa webhook: заказ %d не найден", order_id)
                    return False

                amount_str = obj.get("amount", {}).get("value", "0")
                try:
                    paid_amount = int(float(amount_str))
                except (TypeError, ValueError):
                    paid_amount = 0

                if paid_amount != order.total_amount:
                    logger.error(
                        "ЮKassa webhook: сумма не совпадает для заказа %d: ожидается %d, получено %d",
                        order_id,
                        order.total_amount,
                        paid_amount,
                    )
                    return False

                if order.status not in (OrderStatus.PAID, OrderStatus.DONE, OrderStatus.CANCELLED):
                    order.status = OrderStatus.PAID
                    order.payment_id = payment_id
                    order.status_updated_at = datetime.now()
                    await session.commit()
                    logger.info("ЮKassa webhook: заказ %d оплачен", order_id)

                    await OrderPaymentService._notify_user(
                        shop_id, order.telegram_user_id, order_id, order.total_amount
                    )

        elif event == "payment.canceled":
            logger.info("ЮKassa webhook: платёж заказа %d отменён", order_id)

        return True

    @staticmethod
    async def _notify_user(
        shop_id: int, telegram_user_id: int, order_id: int, amount: int
    ) -> None:
        """Уведомляет покупателя об оплате через бота магазина."""
        from app.bot.bot import get_bot

        bot = get_bot(shop_id)
        if bot is None:
            return

        try:
            await bot.send_message(
                telegram_user_id,
                f"✅ <b>Оплата получена!</b>\n\n"
                f"Заказ №{order_id} на сумму <b>{amount} ₽</b> оплачен.\n"
                "Мы свяжемся с вами для подтверждения доставки.",
            )
        except Exception:
            logger.exception("Не удалось уведомить покупателя по заказу %d", order_id)
