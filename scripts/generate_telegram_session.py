"""Интерактивно создаёт Telethon StringSession для channel backfill.

Секреты не принимаются аргументами командной строки и не записываются на диск.
Запускайте скрипт только на доверенном компьютере.
"""

from __future__ import annotations

import getpass
import re

from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def read_api_id() -> int:
    raw = input("TELEGRAM_API_ID: ").strip()
    if not raw.isdigit() or int(raw) <= 0:
        raise SystemExit("TELEGRAM_API_ID должен быть положительным числом")
    return int(raw)


def read_api_hash() -> str:
    value = getpass.getpass("TELEGRAM_API_HASH (ввод скрыт): ").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{32}", value):
        raise SystemExit("TELEGRAM_API_HASH должен содержать 32 шестнадцатеричных символа")
    return value


def main() -> None:
    print(
        "Создание TELEGRAM_SESSION. После API_ID/API_HASH Telegram запросит "
        "номер телефона, одноразовый код и, если включено, пароль 2FA."
    )
    api_id = read_api_id()
    api_hash = read_api_hash()

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        if not client.is_user_authorized():
            raise SystemExit("Не удалось авторизовать Telegram-аккаунт")
        session = client.session.save()

    print("\nСессия создана. Сохраните следующую строку только в секретном .env:")
    print(f"TELEGRAM_API_ID={api_id}")
    print("TELEGRAM_API_HASH=<используйте введённое значение>")
    print(f"TELEGRAM_SESSION={session}")
    print("\nНе отправляйте TELEGRAM_API_HASH и TELEGRAM_SESSION в чат или Git.")


if __name__ == "__main__":
    main()
