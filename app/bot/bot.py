from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from app.core.config import settings
from app.bot.handlers import router
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.database.db import init_db
from app.database.seed import seed_if_empty

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from app.core.config import settings
from app.bot.handlers import router
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.database.db import init_db
from app.database.seed import seed_if_empty

logger = logging.getLogger(__name__)

_bot_instance: Bot | None = None


def get_bot() -> Bot | None:
    """Возвращает экземпляр бота (для webhook-уведомлений)."""
    return _bot_instance


def create_bot() -> Bot:
    """
    Создание экземпляра Telegram Bot.
    Если указан BOT_PROXY — использует его для обхода блокировки.
    """

    session = None

    if settings.bot_proxy:
        session = AiohttpSession(proxy=settings.bot_proxy)
        logger.info("Используется прокси: %s", settings.bot_proxy)

    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        ),
        session=session,
    )


def create_dispatcher() -> Dispatcher:
    """
    Создание Dispatcher.
    """

    dp = Dispatcher()

    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())

    dp.include_router(router)

    return dp


async def start_bot() -> None:
    """
    Запуск Telegram-бота.
    """

    global _bot_instance

    await init_db()
    await seed_if_empty()

    _bot_instance = create_bot()
    dp = create_dispatcher()

    logger.info("Telegram Bot успешно запущен")

    await dp.start_polling(_bot_instance)
