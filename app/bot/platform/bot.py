import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
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
from app.services.subscription_payment_service import SubscriptionPaymentService
from app.services.admin_user_service import AdminUserService
from app.bot.bot import start_shop_bot

logger = logging.getLogger(__name__)


class OnboardingStates(StatesGroup):
    waiting_for_token = State()


_TOKEN_CHECK_TIMEOUT = 10  # секунд


async def _validate_bot_token(token: str) -> dict | None:
    """Проверяет токен прямым HTTP-запросом к Telegram API.

    Использует тот же прокси, что и боты магазинов — без него запрос
    к api.telegram.org будет висеть на VPS в РФ.
    """
    import aiohttp

    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        timeout = aiohttp.ClientTimeout(total=_TOKEN_CHECK_TIMEOUT)
        connector: aiohttp.BaseConnector | None = None
        proxy = settings.bot_proxy

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, proxy=proxy) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    return None
                r = data["result"]
                return {
                    "id": r["id"],
                    "username": r["username"],
                    "first_name": r["first_name"],
                }
    except (asyncio.TimeoutError, aiohttp.ClientError) as e:
        logger.warning("Сеть/таймаут при проверке токена: %s", e)
        return None
    except Exception:
        logger.exception("Ошибка проверки токена")
        return None


def _main_menu(is_new: bool = True) -> ReplyKeyboardMarkup:
    btn_text = "🚀 Создать магазин" if is_new else "🚀 Создать ещё магазин"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=btn_text)],
            [KeyboardButton(text="📋 Мои магазины"), KeyboardButton(text="💳 Подписка")],
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
            "❌ Не удалось проверить токен.\n\n"
            "Возможные причины:\n"
            "• Токен скопирован не полностью\n"
            "• Telegram временно недоступен\n\n"
            "Попробуйте ещё раз через минуту."
        )
        return

    shop = await ShopService.create(
        name=bot_info["first_name"],
        bot_token=token,
        owner_telegram_id=message.from_user.id,
    )

    await AdminUserService.add(
        shop_id=shop["id"],
        telegram_user_id=message.from_user.id,
        display_name=message.from_user.full_name,
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

    admin_url = settings.admin_panel_url
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

    text += "Что нужно сделать:\n"
    text += "1. Узнайте свой Telegram ID у @userinfobot — он понадобится для входа в админку\n"
    text += "2. Зайдите в админ-панель — код входа придёт от бота @{}\n".format(bot_info["username"])
    text += "3. Добавьте товары, настройте каталог\n"
    text += "4. Откройте бота @{} — нажмите /start\n".format(bot_info["username"])

    kb_rows = []
    if admin_url:
        kb_rows.append([InlineKeyboardButton(text="📊 Открыть админ-панель", url=admin_url)])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None

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


async def on_subscription(message: Message) -> None:
    """Показывает статус подписки и доступные тарифы для оплаты."""
    tg_id = message.from_user.id
    shops = await ShopService.get_all()
    user_shops = [s for s in shops if s["owner_telegram_id"] == tg_id]

    if not user_shops:
        await message.answer(
            "У вас пока нет магазинов для оплаты подписки.",
            reply_markup=_main_menu(),
        )
        return

    if len(user_shops) == 1:
        await _show_subscription_for_shop(message, user_shops[0])
    else:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"🏪 {s['name']}",
                        callback_data=f"sub_shop:{s['id']}",
                    )
                ]
                for s in user_shops
            ]
        )
        await message.answer(
            "Выберите магазин для управления подпиской:",
            reply_markup=kb,
        )


async def _show_subscription_for_shop(message: Message | CallbackQuery, shop: dict) -> None:
    shop_id = shop["id"]
    sub = await SubscriptionService.get_active_subscription(shop_id)

    if sub and sub["is_active"]:
        status_line = f"✅ <b>Активна</b>\nДействует до: <b>{sub['expires_at'][:10]}</b>"
    else:
        status_line = "❌ <b>Истекла</b> — бот остановлен"

    plans = await SubscriptionService.get_plans()

    if not plans:
        text = (
            f"🏪 <b>{shop['name']}</b> (ID: {shop_id})\n\n"
            f"Статус подписки: {status_line}\n\n"
            f"Тарифы не настроены. Обратитесь к администратору."
        )
        await (message.answer if isinstance(message, Message) else message.message.answer)(
            text, reply_markup=_main_menu(is_new=False)
        )
        return

    features = plans[0].get("features", [])

    text = (
        f"🏪 <b>{shop['name']}</b> (ID: {shop_id})\n\n"
        f"Статус подписки: {status_line}\n\n"
        f"{'---' * 10}\n"
        f"📦 <b>Тариф: 5000 ₽ / месяц</b>\n\n"
    )

    for feature in features:
        text += f"  ✅ {feature}\n"

    text += f"\n{'---' * 10}\n"
    text += "<b>Выберите период оплаты:</b>\n\n"

    kb_rows = []
    for plan in plans:
        if plan["description"]:
            text += f"🔸 <b>{plan['name']}</b> — {int(plan['price']):,} ₽\n"
            text += f"<i>{plan['description']}</i>\n\n"
        else:
            text += f"🔸 <b>{plan['name']}</b> — {int(plan['price']):,} ₽\n\n"

        if settings.yookassa_enabled:
            kb_rows.append([
                InlineKeyboardButton(
                    text=f"💳 {plan['name']} — {int(plan['price']):,} ₽".replace(",", " "),
                    callback_data=f"pay:{shop_id}:{plan['id']}",
                )
            ])

    if not settings.yookassa_enabled:
        text += "⚠️ Оплата временно недоступна. Обратитесь к администратору."

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None

    send = message.answer if isinstance(message, Message) else message.message.answer
    await send(text, reply_markup=kb, disable_web_page_preview=True)


async def on_pay(callback: CallbackQuery) -> None:
    """Создаёт платёж через ЮKassa и отправляет ссылку на оплату."""
    _, shop_id_str, plan_id_str = callback.data.split(":")
    shop_id = int(shop_id_str)
    plan_id = int(plan_id_str)

    if not settings.yookassa_enabled:
        await callback.answer("Оплата не настроена", show_alert=True)
        return

    await callback.answer("Создаю платёж...")

    result = await SubscriptionPaymentService.create_payment(
        shop_id=shop_id,
        plan_id=plan_id,
    )

    if result is None:
        await callback.message.answer(
            "❌ Не удалось создать платёж. Попробуйте позже или обратитесь к администратору."
        )
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=result["confirmation_url"])],
        ]
    )

    await callback.message.answer(
        "👇 Нажмите кнопку ниже для перехода к оплате.\n\n"
        "После оплаты подписка активируется автоматически.",
        reply_markup=kb,
    )


async def on_subscription_shop(callback: CallbackQuery) -> None:
    """Показывает подписку для конкретного магазина (выбор из списка)."""
    shop_id = int(callback.data.split(":")[1])
    shop = await ShopService.get(shop_id)

    if shop is None:
        await callback.answer("Магазин не найден", show_alert=True)
        return

    await _show_subscription_for_shop(callback, shop)


def get_platform_router() -> Dispatcher:
    """Создаёт и настраивает Dispatcher для платформенного бота."""
    dp = Dispatcher()

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(
        on_create_shop,
        F.text.in_(["🚀 Создать магазин", "🚀 Создать ещё магазин"]),
    )
    dp.message.register(on_my_shops, F.text == "📋 Мои магазины")
    dp.message.register(on_subscription, F.text == "💳 Подписка")
    dp.callback_query.register(on_enter_token, F.data == "enter_token")
    dp.callback_query.register(
        on_subscription_shop, F.data.startswith("sub_shop:")
    )
    dp.callback_query.register(on_pay, F.data.startswith("pay:"))
    dp.message.register(on_token_received, StateFilter(OnboardingStates.waiting_for_token))

    return dp
