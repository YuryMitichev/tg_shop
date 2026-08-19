#!/usr/bin/env python3
"""Production health monitor with deduplicated Telegram alerts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

VERSION = 1
ENV_FILE = Path("/root/tg_shop/.env")
STATE_DIR = Path("/var/lib/tg-shop-monitor")
STATE_FILE = STATE_DIR / "state.json"
LOCK_FILE = STATE_DIR / "monitor.lock"
REMINDER_SECONDS = 6 * 60 * 60
BACKUP_MAX_AGE_SECONDS = 36 * 60 * 60
DISK_WARNING_PERCENT = 80
CONTAINERS = (
    "tg_shop_db", "tg_shop_backup", "tg_shop_bot", "tg_shop_admin",
    "tg_shop_platform_admin", "tg_shop_xray", "tg_shop_caddy",
)


def read_env_value(name: str) -> str:
    """Read one dotenv value without executing the file as shell code."""
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        return value
    return ""


def run(command: list[str]) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=15)
    return result.stdout.strip()


def collect_issues(force_failure: bool = False) -> list[str]:
    issues: list[str] = []
    for container in CONTAINERS:
        try:
            state = json.loads(run(["docker", "inspect", container]))[0]["State"]
            if not state.get("Running"):
                issues.append(f"Контейнер {container} остановлен")
                continue
            health = state.get("Health", {}).get("Status")
            if health and health != "healthy":
                issues.append(f"Контейнер {container}: {health}")
        except (subprocess.SubprocessError, json.JSONDecodeError, KeyError, IndexError):
            issues.append(f"Не удалось проверить контейнер {container}")

    try:
        last_success = int(run(["docker", "exec", "tg_shop_backup", "cat", "/backups/last_success"]))
        age = int(time.time()) - last_success
        if age >= BACKUP_MAX_AGE_SECONDS:
            issues.append(f"Последний успешный бэкап старше 36 часов ({age // 3600} ч.)")
    except (subprocess.SubprocessError, ValueError):
        issues.append("Не удалось определить время последнего бэкапа")

    disk = shutil.disk_usage("/")
    disk_percent = round(disk.used * 100 / disk.total)
    if disk_percent >= DISK_WARNING_PERCENT:
        issues.append(f"Диск заполнен на {disk_percent}%")

    app_url = read_env_value("APP_BASE_URL").rstrip("/") + "/health"
    if app_url != "/health":
        try:
            with urllib.request.urlopen(app_url, timeout=10) as response:
                if response.status != 200:
                    issues.append(f"Внешняя проверка приложения вернула HTTP {response.status}")
        except Exception:
            issues.append("Приложение недоступно по внешнему адресу")

    if force_failure:
        issues.append("Тестовая ошибка мониторинга")
    return sorted(set(issues))


def send_telegram(text: str) -> None:
    token = read_env_value("BOT_TOKEN")
    chat_id = read_env_value("MANAGER_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("BOT_TOKEN or MANAGER_CHAT_ID is missing")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    last_error: Exception | None = None
    for delay in (0, 2, 5):
        if delay:
            time.sleep(delay)
        try:
            request = urllib.request.Request(url, data=body, method="POST")
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.load(response)
            if not payload.get("ok"):
                raise RuntimeError("Telegram API rejected the alert")
            return
        except Exception as error:
            last_error = error
    raise RuntimeError("Telegram alert failed after 3 attempts") from last_error


def load_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if data.get("version") == VERSION:
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"version": VERSION, "issues": [], "last_alert": 0}


def save_state(issues: list[str], last_alert: int) -> None:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": VERSION, "issues": issues, "last_alert": last_alert}), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(STATE_FILE)


def notification_for(issues: list[str], previous: list[str], last_alert: int, now: int) -> str | None:
    if issues and (issues != previous or now - last_alert >= REMINDER_SECONDS):
        return "🚨 TG Shop: обнаружена проблема:\n\n• " + "\n• ".join(issues)
    if not issues and previous:
        return "✅ TG Shop: работа восстановлена, все проверки проходят."
    return None


def main() -> int:
    import fcntl

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--send-test", action="store_true")
    parser.add_argument("--force-failure", action="store_true")
    args = parser.parse_args()

    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with LOCK_FILE.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("monitor_already_running=true")
            return 0

        issues = collect_issues(args.force_failure)
        if args.dry_run:
            print(json.dumps({"ok": not issues, "issue_count": len(issues)}, ensure_ascii=False))
            return 1 if issues else 0
        if args.send_test:
            send_telegram("✅ TG Shop: тестовые уведомления работают.")
            print("test_alert=sent")
            return 0

        now = int(time.time())
        state = load_state()
        previous = state.get("issues", [])
        last_alert = int(state.get("last_alert", 0))
        notification = notification_for(issues, previous, last_alert, now)
        if notification:
            send_telegram(notification)
            last_alert = now
        save_state(issues, last_alert)
        print(json.dumps({"ok": not issues, "issue_count": len(issues)}, ensure_ascii=False))
        return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
