import asyncio

import uvicorn

from app.bot.bot import start_all_bots
from app.api.main import app
from app.core.config import settings
from app.core.logging import setup_logging


setup_logging(debug=settings.debug)


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
        start_all_bots(),
        server.serve(),
    )


def run():

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
