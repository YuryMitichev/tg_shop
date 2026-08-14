import base64
import logging
import uuid
from typing import Any

import aiohttp

from app.core.config import settings

logger = logging.getLogger(__name__)

API_URL = "https://api.yookassa.ru/v3"


class YooKassaClient:
    """
    Клиент ЮKassa для приёма платежей.

    Документация: https://yookassa.ru/developers/api
    """

    @staticmethod
    def _auth_header(
        shop_id: str | None = None,
        secret_key: str | None = None,
    ) -> str:
        if shop_id and secret_key:
            credentials = f"{shop_id}:{secret_key}"
        else:
            credentials = f"{settings.yookassa_shop_id}:{settings.yookassa_secret_key}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    @staticmethod
    async def create_payment(
        amount_rub: float,
        description: str,
        return_url: str,
        metadata: dict[str, str],
        shop_id: str | None = None,
        secret_key: str | None = None,
        receipt: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Создаёт платёж.

        Если переданы shop_id и secret_key — используются per-shop ключи магазина.
        Иначе — глобальные ключи платформы (для подписок).

        Если передан idempotency_key — он используется как Idempotence-Key:
        повторный запрос с тем же ключом возвращает уже созданный платёж.
        Иначе генерируется новый UUID (повторный запрос создаст дубль).

        Возвращает dict:
        - payment_id: str
        - confirmation_url: str

        При ошибке возвращает None.
        """
        headers = {
            "Authorization": YooKassaClient._auth_header(shop_id, secret_key),
            "Idempotence-Key": idempotency_key or str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

        payload = {
            "amount": {
                "value": f"{amount_rub:.2f}",
                "currency": "RUB",
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": return_url,
            },
            "description": description,
            "metadata": metadata,
        }

        if receipt is not None:
            payload["receipt"] = receipt

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{API_URL}/payments",
                    headers=headers,
                    json=payload,
                ) as resp:
                    data = await resp.json()

            if resp.status == 200:
                confirmation_url = (
                    data.get("confirmation", {}).get("confirmation_url")
                )
                return {
                    "payment_id": data["id"],
                    "confirmation_url": confirmation_url,
                }

            logger.error("ЮKassa create_payment: статус %d, ответ: %s", resp.status, data)
            return None

        except Exception:
            logger.exception("ЮKassa create_payment: ошибка запроса")
            return None

    @staticmethod
    async def get_payment(
        payment_id: str,
        shop_id: str | None = None,
        secret_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Возвращает статус платежа по ID."""
        headers = {
            "Authorization": YooKassaClient._auth_header(shop_id, secret_key),
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{API_URL}/payments/{payment_id}",
                    headers=headers,
                ) as resp:
                    data = await resp.json()

            if resp.status == 200:
                return data

            logger.error("ЮKassa get_payment: статус %d, ответ: %s", resp.status, data)
            return None

        except Exception:
            logger.exception("ЮKassa get_payment: ошибка запроса")
            return None
