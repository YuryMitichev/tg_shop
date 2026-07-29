import hashlib
from typing import Any

import aiohttp

from app.core.config import settings

API_URL = "https://securepay.tinkoff.ru/v2"


def _generate_token(params: dict[str, Any], password: str) -> str:
    """
    Токен Тинькофф: SHA-256 от значений всех параметров
    (кроме Token), отсортированных по ключу, + Password.
    """
    token_data = {k: v for k, v in params.items() if k != "Token"}
    token_data["Password"] = password

    concatenated = "".join(
        str(token_data[key])
        for key in sorted(token_data.keys())
    )

    return hashlib.sha256(concatenated.encode("utf-8")).hexdigest()


def verify_token(params: dict[str, Any], password: str) -> bool:
    """Проверка токена из вебхука Тинькофф."""
    token = params.get("Token")
    if not token:
        return False

    expected = _generate_token(params, password)
    return expected == token


class TinkoffClient:
    """
    Клиент эквайринга Тинькофф.

    Документация: https://www.tinkoff.ru/kassa/dev/
    """

    @staticmethod
    def _add_token(payload: dict[str, Any]) -> dict[str, Any]:
        payload = {**payload, "TerminalKey": settings.tinkoff_terminal_key}
        payload["Token"] = _generate_token(payload, settings.tinkoff_password)
        return payload

    @staticmethod
    async def init_payment(
        order_id: int,
        amount_rub: int,
        description: str,
        notification_url: str,
    ) -> dict[str, Any] | None:
        """
        Создание платежа.

        Возвращает dict с PaymentId, PaymentURL и т.д.
        При ошибке возвращает None.
        """
        payload = {
            "Amount": amount_rub * 100,
            "OrderId": str(order_id),
            "Description": description,
            "DATA": {
                "NotificationURL": notification_url,
            },
        }

        payload = TinkoffClient._add_token(payload)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_URL}/Init/",
                json=payload,
            ) as resp:
                data = await resp.json()

        if data.get("Success"):
            return data

        return None

    @staticmethod
    async def get_qr(payment_id: str) -> dict[str, Any] | None:
        """
        Получение QR-кода для оплаты через СБП.

        Возвращает dict с ключами:
        - QrCode: base64-кодированный PNG
        - PaymentUrl: ссылка для оплаты
        """
        payload = {"PaymentId": payment_id}
        payload = TinkoffClient._add_token(payload)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_URL}/GetQr/",
                json=payload,
            ) as resp:
                data = await resp.json()

        if data.get("Success"):
            return data

        return None

    @staticmethod
    async def get_payment_state(payment_id: str) -> str | None:
        """Получение статуса платежа. Возвращает строку статуса."""
        payload = {"PaymentId": payment_id}
        payload = TinkoffClient._add_token(payload)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_URL}/GetState/",
                json=payload,
            ) as resp:
                data = await resp.json()

        if data.get("Success"):
            return data.get("Status")

        return None
