import logging

from app.core.config import settings
from app.services.platform_settings_service import PlatformSettingsService
from app.services.shop_service import ShopService
from app.services.subscription_service import SubscriptionService
from app.services.yookassa_client import YooKassaClient

logger = logging.getLogger(__name__)


class SubscriptionPaymentService:
    """Связывает оплату ЮKassa с подписками магазинов."""

    @staticmethod
    async def create_payment(
        shop_id: int,
        plan_id: int,
    ) -> dict | None:
        """
        Создаёт платёж для оплаты подписки.

        Возвращает dict:
        - payment_id: str
        - confirmation_url: str

        При ошибке возвращает None.
        """
        plan = await SubscriptionService.get_plan(plan_id)
        if plan is None or plan["is_trial"]:
            logger.warning("Попытка оплаты триального тарифа %d", plan_id)
            return None

        shop = await ShopService.get(shop_id)
        if shop is None:
            return None

        creds = await PlatformSettingsService.get_yookassa_credentials()
        if creds is None:
            logger.error(
                "Не настроены ключи ЮKassa платформы для оплаты подписки магазина %d",
                shop_id,
            )
            return None

        return_url = settings.admin_panel_url or settings.app_base_url or "https://t.me"

        description = f"Подписка «{plan['name']}» — {plan['duration_days']} дней (магазин «{shop['name']}»)"

        receipt = None
        customer_email = settings.receipt_email
        if customer_email:
            receipt = {
                "customer": {"email": customer_email},
                "items": [
                    {
                        "description": description[:128],
                        "quantity": "1",
                        "amount": {
                            "value": f"{plan['price']:.2f}",
                            "currency": "RUB",
                        },
                        "vat_code": settings.yookassa_default_vat_code,
                    }
                ],
            }

        result = await YooKassaClient.create_payment(
            amount_rub=plan["price"],
            description=description,
            return_url=return_url,
            metadata={
                "type": "subscription",
                "shop_id": str(shop_id),
                "plan_id": str(plan_id),
            },
            shop_id=creds[0],
            secret_key=creds[1],
            receipt=receipt,
        )

        if result is None:
            logger.error("Не удалось создать платёж для магазина %d", shop_id)

        return result

    @staticmethod
    async def process_webhook(data: dict) -> bool:
        """
        Обрабатывает вебхук от ЮKassa.

        Ожидает формат:
        {
          "event": "payment.succeeded",
          "object": {
            "id": "...",
            "status": "succeeded",
            "metadata": {"shop_id": "2", "plan_id": "3"},
          }
        }
        """
        event = data.get("event")
        obj = data.get("object")

        if not event or not obj:
            logger.warning("ЮKassa webhook: некорректный формат: %s", data)
            return False

        if event not in ("payment.succeeded", "payment.canceled"):
            logger.info("ЮKassa webhook: игнорирую событие %s", event)
            return True

        metadata = obj.get("metadata", {})
        payment_id = obj.get("id")

        try:
            shop_id = int(metadata.get("shop_id", 0))
            plan_id = int(metadata.get("plan_id", 0))
        except (TypeError, ValueError):
            logger.warning("ЮKassa webhook: некорректные metadata: %s", metadata)
            return False

        if not shop_id or not plan_id:
            logger.warning("ЮKassa webhook: нет shop_id или plan_id в metadata")
            return False

        if event == "payment.succeeded":
            result = await SubscriptionService.activate_paid_subscription(
                shop_id, plan_id, payment_id
            )

            if result is None:
                logger.error(
                    "ЮKassa webhook: не удалось активировать подписку для магазина %d",
                    shop_id,
                )
                return False

            logger.info(
                "ЮKassa webhook: подписка магазина %d активирована до %s",
                shop_id,
                result["expires_at"],
            )

            await SubscriptionPaymentService._notify_shop_owner(
                shop_id, plan_id, result["expires_at"]
            )

        elif event == "payment.canceled":
            logger.info("ЮKassa webhook: платёж %s отменён", payment_id)

        return True

    @staticmethod
    async def _notify_shop_owner(
        shop_id: int, plan_id: int, expires_at: str
    ) -> None:
        """Уведомляет владельца магазина об успешной оплате через платформенного бота."""
        from app.bot.bot import _bot_registry
        from app.core.config import settings as cfg

        if not cfg.platform_bot_token:
            return

        shop = await ShopService.get(shop_id)
        if shop is None or shop["owner_telegram_id"] is None:
            return

        plan = await SubscriptionService.get_plan(plan_id)
        plan_name = plan["name"] if plan else "тариф"

        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode

        bot = Bot(
            token=cfg.platform_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )

        try:
            await bot.send_message(
                shop["owner_telegram_id"],
                f"✅ <b>Подписка оплачена!</b>\n\n"
                f"Тариф: «{plan_name}»\n"
                f"Действует до: {expires_at[:10]}\n\n"
                f"Спасибо за оплату! 🎉",
            )
        except Exception:
            logger.exception("Не удалось уведомить владельца магазина %d", shop_id)
        finally:
            await bot.session.close()
