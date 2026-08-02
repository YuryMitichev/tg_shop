import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from app.core.config import settings
from app.services.shop_service import ShopService
from app.services.subscription_service import SubscriptionService
from app.bot.bot import start_shop_bot

logger = logging.getLogger(__name__)


class OnboardingStates(StatesGroup):
    waiting_for_token = State()


async def _validate_bot_token(token: str) -> dict | None:
    """Проверяет токен через Telegram API. Возвращает инфо о боте или None."""
    try:
        bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        me = await bot.get_me()
        await bot.session.close()
        return {
            "id": me.id,
            "username": me.username,
            "first_name": me.first_name,
        }
    except TelegramUnauthorizedError:
        return None
    except Exception:
        logger.exception("Ошибка проверки токена")
        return None


def _main_menu(is_new: bool = True) -> ReplyKeyboardMarkup:
    btn_text = "🚀 Создать магазин" if is_new else "🚀 Создать ещё магазин"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=btn_text)],
            [KeyboardButton(text="📋 Мои магазины")],
        ],
        resize_keyboard=True,
    )


def _botfather_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Открыть @BotFather", url="https://t.me/BotFather")],
            [InlineKeyboardButton(text="✅ Я создал бота, ввести токен", callback_data="enter_token")],
        ]
    )


async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    tg_id = message.from_user.id

    shops = await ShopService.get_all()
    user_shops = [s for s in shops if s["owner_telegram_id"] == tg_id]

    if user_shops:
        text = (
            f"👋 Привет! У вас {len(user_shops)} магазин(ов) в системе.\n\n"
            "Выберите действие:"
        )
        kb = _main_menu(is_new=False)
    else:
        text = (
            "👋 <b>Добро пожаловать!</b>\n\n"
            "Это платформа для создания магазинов в Telegram.\n"
            "За пару минут вы получите:\n"
            "  🛍 Каталог товаров с фото\n"
            "  🛒 Корзину и оформление заказов\n"
            "  👥 CRM и рассылки\n"
            "  📊 Админ-панель\n\n"
            "🎁 <b>7 дней бесплатно</b> — попробуйте всё прямо сейчас!"
        )
        kb = _main_menu(is_new=True)

    await message.answer(text, reply_markup=kb)


async def on_create_shop(message: Message, state: FSMContext) -> None:
    text = (
        "<b>Шаг 1. Создайте бота в @BotFather</b>\n\n"
        "1. Откройте @BotFather\n"
        "2. Отправьте команду <code>/newbot</code>\n"
        "3. Введите название бота (например: <i>Мой магазин</i>)\n"
        "4. Введите username (должен заканчиваться на <b>bot</b>)\n"
        "5. BotFather пришлёт <b>токен</b> — скопируйте его\n\n"
        "После этого нажмите кнопку ниже 👇"
    )
    await message.answer(text, reply_markup=_botfather_kb())


async def on_enter_token(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(
        "📎 Отправьте сюда <b>токен</b> вашего бота.\n\n"
        "Он выглядит так: <code>123456789:ABCdef...</code>\n\n"
        "Просто вставьте его следующим сообщением.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(OnboardingStates.waiting_for_token)
    await callback.answer()


async def on_token_received(message: Message, state: FSMContext) -> None:
    token = message.text.strip()

    if not token or ":" not in token:
        await message.answer(
            "❌ Это не похоже на токен.\n"
            "Токен выглядит так: <code>123456789:ABCdef...</code>\n\n"
            "Попробуйте ещё раз."
        )
        return

    existing = await ShopService.get_by_bot_token(token)
    if existing:
        await message.answer("❌ Этот токен уже используется в системе.")
        await state.clear()
        return

    await message.answer("⏳ Проверяю токен...")

    bot_info = await _validate_bot_token(token)
    if bot_info is None:
        await message.answer(
            "❌ Неверный токен. Проверьте, что вы скопировали его полностью из @BotFather."
        )
        return

    shop = await ShopService.create(
        name=bot_info["first_name"],
        bot_token=token,
        owner_telegram_id=message.from_user.id,
    )

    await SubscriptionService.start_trial(shop["id"])

    await message.answer(
        f"✅ <b>Магазин «{shop['name']}» создан!</b>\n\n"
        f"🎁 Активирован бесплатный период — <b>7 дней</b>\n\n"
        "🚀 Запускаю бота..."
    )

    try:
        await start_shop_bot(shop["id"])
    except Exception:
        logger.exception("Не удалось запустить бота для магазина %d", shop["id"])
        await message.answer(
            "⚠️ Бот создан, но не удалось запустить его автоматически.\n"
            "Обратитесь к администратору платформы."
        )
        await state.clear()
        return

    admin_url = None
    if settings.app_base_url:
        admin_url = f"{settings.app_base_url.rstrip('/')}/admin/"

    webapp_url = None
    if settings.app_base_url:
        webapp_url = f"{settings.app_base_url.rstrip('/')}/app/"

    text = (
        f"🎉 <b>Готово! Ваш магазин работает!</b>\n\n"
        f"🤖 Бот: @{bot_info['username']}\n"
        f"🎁 Подписка: 7 дней бесплатно\n\n"
    )

    if admin_url:
        text += f"📊 <b>Админ-панель:</b>\n{admin_url}\n\n"
    if webapp_url:
        text += f"📱 <b>Мини-приложение:</b>\n{webapp_url}\n\n"

    text += "Что можно сделать сейчас:\n"
    text += "1. Откройте бота @{} — нажмите /start\n".format(bot_info["username"])
    text += "2. Зайдите в админ-панель — добавьте товары\n"
    text += "3. Настройте каталог и цены\n"

    kb_rows = [[InlineKeyboardButton(text="📊 Открыть админ-панель", url=admin_url)]]
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await message.answer(text, reply_markup=kb, disable_web_page_preview=True)

    await state.clear()


async def on_my_shops(message: Message) -> None:
    tg_id = message.from_user.id
    shops = await ShopService.get_all()
    user_shops = [s for s in shops if s["owner_telegram_id"] == tg_id]

    if not user_shops:
        await message.answer("У вас пока нет магазинов.", reply_markup=_main_menu())
        return

    for shop in user_shops:
        sub = await SubscriptionService.get_active_subscription(shop["id"])
        status = "✅ Активна" if sub and sub["is_active"] else "❌ Истекла"
        expires = sub["expires_at"][:10] if sub else "—"

        await message.answer(
            f"🏪 <b>{shop['name']}</b>\n"
            f"   ID: {shop['id']}\n"
            f"   Статус: {'🟢 активен' if shop['is_active'] else '🔴 отключён'}\n"
            f"   Подписка: {status}\n"
            f"   До: {expires}\n"
        )

    await message.answer("Выберите действие:", reply_markup=_main_menu(is_new=False))


def get_platform_router() -> Dispatcher:
    """Создаёт и настраивает Dispatcher для платформенного бота."""
    dp = Dispatcher()

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(
        on_create_shop,
        F.text.in_(["🚀 Создать магазин", "🚀 Создать ещё магазин"]),
    )
    dp.message.register(on_my_shops, F.text == "📋 Мои магазины")
    dp.callback_query.register(on_enter_token, F.data == "enter_token")
    dp.message.register(on_token_received, StateFilter(OnboardingStates.waiting_for_token))

    return dp
