import json
import logging
import sys
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Receive, Scope, Send

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return request_id_var.get()


class JsonFormatter(logging.Formatter):
    """JSON-форматтер для продакшена — одна строка JSON на запись."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        rid = request_id_var.get()
        if rid:
            log_entry["request_id"] = rid

        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "shop_id"):
            log_entry["shop_id"] = record.shop_id

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class ReadableFormatter(logging.Formatter):
    """Читаемый формат для dev."""

    def format(self, record: logging.LogRecord) -> str:
        rid = request_id_var.get()
        rid_str = f" [{rid[:8]}]" if rid else ""
        return (
            f"{self.formatTime(record, '%H:%M:%S')} "
            f"{record.levelname:<7} "
            f"{record.name}:{record.lineno}{rid_str} — {record.getMessage()}"
        )


def setup_logging(debug: bool = False) -> None:
    """Настраивает единый конфиг логирования.

    debug=True  → читаемый формат (для разработки)
    debug=False → JSON-формат (для продакшена / лог-агрегаторов)
    """
    level = logging.DEBUG if debug else logging.INFO
    formatter = ReadableFormatter() if debug else JsonFormatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.INFO if debug else logging.WARNING)

    if debug:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


class RequestIdMiddleware:
    """ASGI middleware: генерирует request_id для каждого HTTP-запроса.

    Принимает X-Request-Id из заголовка или создаёт новый UUID.
    Сохраняет в contextvar (доступно из любого лога в рамках запроса).
    Добавляет X-Request-Id в ответ.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(
            (k.decode().lower(), v.decode())
            for k, v in scope.get("headers", [])
        )

        rid = headers.get("x-request-id") or str(uuid.uuid4())
        token = request_id_var.set(rid)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_var.reset(token)
