import asyncio
import logging

from app.bot.bot import start_bot
from app.core.config import settings


logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def main():

    try:
        asyncio.run(start_bot())

    except KeyboardInterrupt:
        logging.info("Работа бота остановлена.")


if __name__ == "__main__":
    main()