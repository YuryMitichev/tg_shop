import asyncio
import logging

import uvicorn

from app.bot.bot import start_bot
from app.api.main import app
from app.core.config import settings


logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


async def main():
    """
    Запуск Telegram-бота и FastAPI (вебхуки Тинькофф) в одном процессе.
    """
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    await asyncio.gather(
        start_bot(),
        server.serve(),
    )


def run():

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        logging.info("Работа бота остановлена.")


if __name__ == "__main__":
    run()
