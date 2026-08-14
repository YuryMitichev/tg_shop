import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.enums import OrderStatus
from app.database.db import async_session
from app.models.order import Order
from app.models.payment import Payment
from app.services.shop_service import ShopService
from app.services.yookassa_client import YooKassaClient

logger = logging.getLogger(__name__)


class OrderPaymentService:
    """Создаёт платежи ЮKassa для заказов и обрабатывает вебхуки."""

    _RESOLVE_MAX_TRIES = 5

    @staticmethod
    def _idempotency_key(order_id: int, attempt: int = 1) -> str:
        """
        Детерминированный ключ идемпотентности одной платёжной попытки.

        Попытка 1 — order:{order_id}:yookassa, последующие — с суффиксом
        номера попытки. Retry той же попытки шлёт тот же ключ (ЮKassa
        возвращает исходный платёж), новая попытка после canceled —
        новый ключ и новый платёж.
        """
        if attempt <= 1:
            return f"order:{order_id}:yookassa"
        return f"order:{order_id}:yookassa:{attempt}"

    @staticmethod
    async def create_payment(shop_id: int, order_id: int) -> dict | None:
        """
        Создаёт платёж ЮKassa для заказа (идемпотентно в рамках попытки).

        Повторный вызов с той же активной (pending) попыткой шлёт в ЮKassa
        тот же Idempotence-Key, поэтому новый intent не создаётся (в т.ч.
        после потери ответа). Если последняя попытка canceled — создаётся
        новая попытка с новым ключом.

        Возвращает dict:
        - payment_id: str
        - confirmation_url: str | None

        При ошибке возвращает None.
        """
        async with async_session() as session:
            order = await session.get(Order, order_id)
            if order is None or order.shop_id != shop_id:
                return None

            if order.status in (OrderStatus.PAID, OrderStatus.DONE, OrderStatus.CANCELLED):
                logger.warning(
                    "Отказ в оплате: заказ %d уже в терминальном статусе %s",
                    order_id,
                    order.status,
                )
                return None

            amount = order.total_amount
            description = f"Заказ №{order_id}"
            customer_phone = order.phone

        creds = await ShopService.get_yookassa_credentials(shop_id)
        if creds is None:
            logger.error("ЮKassa ключи не настроены для магазина %d", shop_id)
            return None

        payment_row = await OrderPaymentService._resolve_payment_row(
            order_id, shop_id, amount
        )
        if payment_row is None:
            return None

        if payment_row.status == "succeeded" and payment_row.provider_payment_id:
            return {
                "payment_id": payment_row.provider_payment_id,
                "confirmation_url": None,
            }

        return_url = settings.webapp_url or settings.admin_panel_url or "https://t.me"

        receipt = None
        customer_email = settings.receipt_email
        if customer_email or customer_phone:
            customer = {}
            if customer_email:
                customer["email"] = customer_email
            if customer_phone:
                customer["phone"] = customer_phone
            receipt = {
                "customer": customer,
                "items": [
                    {
                        "description": description[:128],
                        "quantity": "1",
                        "amount": {
                            "value": f"{float(amount):.2f}",
                            "currency": "RUB",
                        },
                        "vat_code": settings.yookassa_default_vat_code,
                        "payment_mode": "full_payment",
                        "payment_subject": "commodity",
                    }
                ],
            }

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
            receipt=receipt,
            idempotency_key=payment_row.idempotency_key,
        )

        if result is None:
            logger.error("Не удалось создать платёж для заказа %d", order_id)
            return None

        await OrderPaymentService._save_payment_id(
            order_id, result["payment_id"], payment_row.idempotency_key
        )

        return result

    @staticmethod
    async def _resolve_payment_row(
        order_id: int, shop_id: int, amount_rub: int
    ) -> Payment | None:
        """
        Возвращает активную платёжную попытку заказа, создавая новую при необходимости.

        - последняя попытка pending/succeeded → переиспользуется
          (retry / double-click / timeout = та же логическая операция);
        - последняя попытка canceled → создаётся НОВАЯ попытка
          (новая логическая операция, новый idempotency key);
        - попыток нет → создаётся попытка 1.

        Конкурентный INSERT ловит IntegrityError по UNIQUE-констрейнтам
        и на следующей итерации переиспользует выигравшую строку —
        защита на уровне БД, а не только Python-проверки.
        """
        for _ in range(OrderPaymentService._RESOLVE_MAX_TRIES):
            async with async_session() as session:
                latest = (
                    await session.execute(
                        select(Payment)
                        .where(Payment.order_id == order_id)
                        .order_by(Payment.attempt.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

                if latest is not None and latest.status in ("pending", "succeeded"):
                    return latest

                next_attempt = 1 if latest is None else latest.attempt + 1
                payment = Payment(
                    order_id=order_id,
                    shop_id=shop_id,
                    provider="yookassa",
                    attempt=next_attempt,
                    idempotency_key=OrderPaymentService._idempotency_key(
                        order_id, next_attempt
                    ),
                    amount_minor=amount_rub * 100,
                    currency="RUB",
                    status="pending",
                )
                session.add(payment)

                try:
                    await session.commit()
                    return payment
                except IntegrityError:
                    await session.rollback()
                    continue

        logger.error(
            "payments: не удалось согласовать попытку оплаты для заказа %d", order_id
        )
        return None

    @staticmethod
    async def _save_payment_id(
        order_id: int, payment_id: str, idempotency_key: str
    ) -> None:
        """Сохраняет provider_payment_id в payments и order.payment_id (dual-write)."""
        async with async_session() as session:
            order = await session.get(Order, order_id)
            if order:
                order.payment_id = payment_id

            result = await session.execute(
                select(Payment).where(Payment.idempotency_key == idempotency_key)
            )
            payment = result.scalar_one_or_none()
            if payment and payment.provider_payment_id is None:
                payment.provider_payment_id = payment_id
                payment.updated_at = datetime.now()

            await session.commit()

    @staticmethod
    async def _mark_payment_status(payment_id: str, status: str) -> None:
        """Синхронизирует статус записи payments по webhook-событию."""
        async with async_session() as session:
            result = await session.execute(
                select(Payment).where(Payment.provider_payment_id == payment_id)
            )
            payment = result.scalar_one_or_none()

            if payment is None:
                logger.warning(
                    "ЮKassa webhook: запись payments для %s не найдена", payment_id
                )
                return

            if payment.status != status:
                payment.status = status
                payment.updated_at = datetime.now()
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

            await OrderPaymentService._mark_payment_status(payment_id, "succeeded")

        elif event == "payment.canceled":
            logger.info("ЮKassa webhook: платёж заказа %d отменён", order_id)
            await OrderPaymentService._mark_payment_status(payment_id, "canceled")

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
