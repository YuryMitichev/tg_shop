import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from app.core.config import settings
from app.bot.handlers import create_main_router
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.bot.middlewares.crm import CrmMiddleware
from app.bot.middlewares.shop import ShopMiddleware
from app.database.db import init_db
from app.services.crm_service import CrmService
from app.services.broadcast_service import BroadcastService
from app.services.order_service import OrderService
from app.services.shop_service import ShopService

logger = logging.getLogger(__name__)

_bot_registry: dict[int, "ShopBot"] = {}

_stopped_shops: set[int] = set()


class ShopBot(Bot):
    """Bot с привязкой к конкретному магазину."""

    shop_id: int = 1

    def __init__(self, *args, shop_id: int = 1, **kwargs):
        super().__init__(*args, **kwargs)
        self.shop_id = shop_id


def get_bot(shop_id: int | None = None) -> Bot | None:
    """Возвращает экземпляр бота по shop_id.

    Если shop_id не указан — возвращает первый доступный бот.
    """
    if shop_id is not None:
        return _bot_registry.get(shop_id)
    if _bot_registry:
        return next(iter(_bot_registry.values()))
    return None


def _create_bot(shop_id: int, token: str) -> ShopBot:
    session = None
    if settings.bot_proxy:
        session = AiohttpSession(proxy=settings.bot_proxy)
        logger.info("Магазин %d: используется прокси %s", shop_id, settings.bot_proxy)

    return ShopBot(
        token=token,
        shop_id=shop_id,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )


def _create_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    dp.message.middleware(ShopMiddleware())
    dp.callback_query.middleware(ShopMiddleware())
    dp.channel_post.middleware(ShopMiddleware())
    dp.edited_channel_post.middleware(ShopMiddleware())
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.message.middleware(CrmMiddleware())
    dp.callback_query.middleware(CrmMiddleware())

    dp.include_router(create_main_router())

    return dp


async def _run_shop_bot(shop_id: int, token: str) -> None:
    """Создаёт и запускает polling для одного бота.

    При падении автоматически перезапускается с экспоненциальной задержкой
    (10с → 15с → 22с → ... → макс 300с).
    """
    retry_delay = 10
    max_delay = 300

    while True:
        if shop_id in _stopped_shops:
            _stopped_shops.discard(shop_id)
            logger.info("Магазин %d: бот остановлен вручную", shop_id)
            return

        bot = _create_bot(shop_id, token)
        dp = _create_dispatcher()
        _bot_registry[shop_id] = bot

        logger.info("Магазин %d: бот запущен", shop_id)

        try:
            await dp.start_polling(bot)
            return
        except Exception:
            logger.exception(
                "Магазин %d: ошибка polling, рестарт через %ds",
                shop_id,
                retry_delay,
            )
            await bot.session.close()
            _bot_registry.pop(shop_id, None)

            if shop_id in _stopped_shops:
                _stopped_shops.discard(shop_id)
                logger.info("Магазин %d: бот остановлен вручную", shop_id)
                return

            await asyncio.sleep(retry_delay)
            retry_delay = min(int(retry_delay * 1.5), max_delay)


async def _backfill_bot_username(shop_id: int, shop: dict | None = None) -> None:
    """Заполняет bot_username для магазина, если его ещё нет в БД."""
    if shop is None:
        shop = await ShopService.get(shop_id)
    if shop is None or shop.get("bot_username"):
        return

    token = await ShopService.get_bot_token(shop_id)
    if token is None:
        return

    try:
        tmp_bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        me = await tmp_bot.get_me()
        await tmp_bot.session.close()
        if me.username:
            await ShopService.update_bot_username(shop_id, me.username)
            logger.info("Магазин %d: bot_username обновлён — @%s", shop_id, me.username)
    except Exception:
        logger.exception("Магазин %d: не удалось получить bot_username", shop_id)


async def start_shop_bot(shop_id: int) -> bool:
    """Динамически запускает бот для магазина."""
    if shop_id in _bot_registry:
        return False

    shop = await ShopService.get(shop_id)
    if shop is None or not shop["is_active"]:
        return False

    token = await ShopService.get_bot_token(shop_id)
    if token is None:
        return False

    if settings.platform_bot_token and token == settings.platform_bot_token:
        logger.info(
            "Магазин %d: токен совпадает с платформенным ботом — пропускаем shop polling",
            shop_id,
        )
        return False

    await _backfill_bot_username(shop_id, shop)

    asyncio.create_task(_run_shop_bot(shop_id, token))
    return True


async def stop_shop_bot(shop_id: int) -> None:
    """Останавливает бот для магазина."""
    _stopped_shops.add(shop_id)
    bot = _bot_registry.get(shop_id)
    if bot:
        await bot.session.close()


async def restart_shop_bot(shop_id: int) -> None:
    """Перезапускает бот для магазина (после смены токена)."""
    await stop_shop_bot(shop_id)
    await asyncio.sleep(1)
    await start_shop_bot(shop_id)


async def _auto_cancel_loop() -> None:
    """Фоновая задача: авто-отмена заказов без смены статуса 14 дней."""
    while True:
        await asyncio.sleep(3600)
        try:
            cancelled = await OrderService.auto_cancel_stale_orders(days=14)
            if cancelled:
                logger.info("Авто-отмена: отменено заказов старше 14 дней: %d", cancelled)
        except Exception:
            logger.exception("Авто-отмена: ошибка")


async def start_all_bots() -> None:
    """Запуск всех активных ботов из БД + фоновых задач."""

    await init_db()

    try:
        cancelled = await OrderService.auto_cancel_stale_orders(days=14)
        if cancelled:
            logger.info("Авто-отмена при запуске: отменено %d заказов", cancelled)
    except Exception:
        logger.exception("Авто-отмена: ошибка при запуске")

    shops = await ShopService.get_all(active_only=True)

    for shop in shops:
        sid = shop["id"]
        await _backfill_bot_username(sid, shop)

        try:
            backfilled = await CrmService.backfill_from_orders(sid)
            if backfilled:
                logger.info("Магазин %d: CRM backfill профилей: %d", sid, backfilled)
        except Exception:
            logger.exception("Магазин %d: CRM ошибка при backfill", sid)

        try:
            tagged = await BroadcastService.auto_tag_all_users(sid)
            if tagged:
                logger.info("Магазин %d: авто-тегов обновлено: %d", sid, tagged)
        except Exception:
            logger.exception("Магазин %d: ошибка при автотегировании", sid)

    asyncio.create_task(_auto_cancel_loop())
    asyncio.create_task(_subscription_check_loop())
    if settings.channel_import_enabled:
        from app.services.channel_import_worker import ChannelImportWorker

        asyncio.create_task(ChannelImportWorker(concurrency=2).run_forever())
        asyncio.create_task(_channel_import_cleanup_loop())
    if settings.channel_product_buttons_enabled:
        from app.services.channel_post_button_worker import ChannelPostButtonWorker

        asyncio.create_task(ChannelPostButtonWorker(concurrency=1).run_forever())
    if settings.channel_attribution_enabled:
        from app.services.channel_metrics_service import ChannelMetricsService

        asyncio.create_task(ChannelMetricsService.run_forever())

    if settings.platform_bot_token:
        asyncio.create_task(_run_platform_bot())
    else:
        logger.warning("PLATFORM_BOT_TOKEN не задан — платформенный бот не запущен")

    if not shops:
        logger.warning("Нет активных магазинов для запуска ботов")
        return

    tasks = []
    for shop in shops:
        token = await ShopService.get_bot_token(shop["id"])
        if not token:
            continue
        if settings.platform_bot_token and token == settings.platform_bot_token:
            logger.info(
                "Магазин %d: токен совпадает с платформенным ботом — пропускаем shop polling",
                shop["id"],
            )
            continue
        tasks.append(_run_shop_bot(shop["id"], token))

    await asyncio.gather(*tasks) if tasks else None


async def _channel_import_cleanup_loop() -> None:
    """Ежедневно удаляет сырые данные закрытых импортов старше 90 дней."""
    from app.services.channel_import_service import ChannelImportService

    while True:
        await asyncio.sleep(24 * 3600)
        try:
            cleaned = await ChannelImportService.cleanup_raw_data(days=90)
            if cleaned:
                logger.info("AI-import retention cleanup: очищено постов %d", cleaned)
        except Exception:
            logger.exception("AI-import retention cleanup failed")


async def _run_platform_bot() -> None:
    """Запускает платформенный бот (registrar) для онбординга."""
    from app.bot.platform.bot import get_platform_router

    session = None
    if settings.bot_proxy:
        session = AiohttpSession(proxy=settings.bot_proxy)

    bot = Bot(
        token=settings.platform_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dp = get_platform_router()

    logger.info("Платформенный бот запущен")

    try:
        await dp.start_polling(bot)
    except Exception:
        logger.exception("Платформенный бот: ошибка polling")
    finally:
        await bot.session.close()


async def _subscription_check_loop() -> None:
    """Фоновая задача: отключает боты с истекшей подпиской + уведомления."""
    from app.services.subscription_service import SubscriptionService
    from app.services.shop_service import ShopService

    notified: set[int] = set()

    while True:
        await asyncio.sleep(3600)
        try:
            expired = await SubscriptionService.get_expired_shops()
            for shop_id in expired:
                logger.info("Подписка магазина %d истекла — останавливаю бота", shop_id)
                await stop_shop_bot(shop_id)
                await SubscriptionService.mark_expired(shop_id)
                notified.discard(shop_id)

            expiring = await SubscriptionService.get_expiring_shops(hours=24)
            for item in expiring:
                sid = item["shop_id"]
                if sid not in notified:
                    notified.add(sid)
                    shop = await ShopService.get(sid)
                    if shop and shop["owner_telegram_id"]:
                        await _send_trial_ending_notice(
                            shop["owner_telegram_id"],
                            shop["name"],
                            item["expires_at"][:10],
                        )

        except Exception:
            logger.exception("Проверка подписок: ошибка")


async def _send_trial_ending_notice(
    owner_telegram_id: int, shop_name: str, expires_at: str
) -> None:
    """Отправляет уведомление об окончании триала через платформенного бота."""
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    if not settings.platform_bot_token:
        return

    bot = Bot(
        token=settings.platform_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    try:
        await bot.send_message(
            owner_telegram_id,
            f"⏰ <b>Триал заканчивается!</b>\n\n"
            f"Магазин «{shop_name}» — бесплатный период истекает <b>{expires_at}</b>.\n\n"
            f"Чтобы бот продолжил работать, оплатите подписку.\n"
            f"Откройте платформенного бота → «💳 Подписка».",
        )
    except Exception:
        logger.exception("Не удалось отправить уведомление об окончании триала")
    finally:
        await bot.session.close()
