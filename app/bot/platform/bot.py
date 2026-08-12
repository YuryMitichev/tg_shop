import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.core.config import settings
from app.services.shop_service import ShopService
from app.services.subscription_service import SubscriptionService
from app.services.subscription_payment_service import SubscriptionPaymentService
from app.services.admin_user_service import AdminUserService
from app.services.offer_agreement_service import (
    OfferAgreementService,
    get_offer_text,
    get_privacy_policy_text,
)
from app.bot.bot import get_bot, start_shop_bot, stop_shop_bot

logger = logging.getLogger(__name__)


class OnboardingStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_token = State()


async def _validate_bot_token(token: str) -> dict | None:
    """Проверяет токен через aiogram.Bot.get_me().

    Использует ту же инфраструктуру соединений, что и боты магазинов
    (включая прокси), вместо отдельного прямого HTTP-запроса.
    """
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.enums import ParseMode

    session = None
    if settings.bot_proxy:
        session = AiohttpSession(proxy=settings.bot_proxy)

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )

    try:
        me = await bot.get_me()
        return {
            "id": me.id,
            "username": me.username or "",
            "first_name": me.first_name,
        }
    except Exception as e:
        logger.warning("Ошибка проверки токена: %s", e)
        return None
    finally:
        await bot.session.close()


def _main_menu(is_new: bool = True) -> ReplyKeyboardMarkup:
    btn_text = "🚀 Создать магазин" if is_new else "🚀 Создать ещё магазин"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=btn_text)],
            [KeyboardButton(text="📋 Мои магазины"), KeyboardButton(text="💳 Подписка")],
            [KeyboardButton(text="📄 Оферта"), KeyboardButton(text="🛠 Поддержка"), KeyboardButton(text="ℹ️ О платформе")],
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


def _shop_actions_kb(shop: dict) -> InlineKeyboardMarkup:
    """Инлайн-кнопки действий для конкретного магазина владельца."""
    shop_id = shop["id"]
    rows: list[list[InlineKeyboardButton]] = []

    rows.append(
        [
            InlineKeyboardButton(text="💳 Подписка", callback_data=f"sub_shop:{shop_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_shop:{shop_id}"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_shop_card(message: Message, shop: dict) -> None:
    """Отправляет карточку магазина с инлайн-кнопками действий."""
    sub = await SubscriptionService.get_active_subscription(shop["id"])
    status = "✅ Активна" if sub and sub["is_active"] else "❌ Истекла"
    expires = sub["expires_at"][:10] if sub else "—"

    bot_username = shop.get("bot_username")

    lines = [
        f"🏪 <b>{shop['name']}</b>",
        f"   ID: {shop['id']}",
        f"   Статус: {'🟢 активен' if shop['is_active'] else '🔴 отключён'}",
        f"   Подписка: {status}",
        f"   До: {expires}",
    ]
    if bot_username:
        lines.append(f"   Бот: @{bot_username}")

    await message.answer(
        "\n".join(lines),
        reply_markup=_shop_actions_kb(shop),
    )


async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    tg_id = message.from_user.id

    user_shops = await ShopService.get_by_owner(tg_id)

    if user_shops:
        await message.answer(
            f"👋 У вас {len(user_shops)} магазин(ов) в системе.\n"
            "Управляйте каждым магазином кнопками в карточках ниже 👇",
            reply_markup=_main_menu(is_new=False),
        )
        for shop in user_shops:
            await _send_shop_card(message, shop)
    else:
        await message.answer(
            "👋 <b>Добро пожаловать!</b>\n\n"
            "Это платформа для создания магазинов в Telegram.\n"
            "Каталог, корзина, заказы, CRM и админ-панель — "
            "всё готово, настройка за 5 минут.\n\n"
            "🎁 <b>7 дней бесплатно</b> — нажмите кнопку ниже 👇",
            reply_markup=_main_menu(is_new=True),
        )


async def on_create_shop(message: Message, state: FSMContext) -> None:
    await message.answer(
        "📝 <b>Как назовём ваш магазин?</b>\n\n"
        "Это название будет отображаться в админ-панели.\n"
        "Например: <i>Свечеваров</i>, <i>Магазин сладостей</i>\n\n"
        "Отправьте название следующим сообщением.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(OnboardingStates.waiting_for_name)


async def on_name_received(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name or len(name) > 100:
        await message.answer(
            "❌ Название должно быть от 1 до 100 символов.\nПопробуйте ещё раз."
        )
        return

    await state.update_data(shop_name=name)

    text = (
        "<b>Отлично! Теперь создайте бота в @BotFather</b>\n\n"
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

    data = await state.get_data()
    shop_name = data.get("shop_name") or bot_info["first_name"]

    shop = await ShopService.create(
        name=shop_name,
        bot_token=token,
        owner_telegram_id=message.from_user.id,
        bot_username=bot_info.get("username"),
    )

    await AdminUserService.add(
        shop_id=shop["id"],
        telegram_user_id=message.from_user.id,
        display_name=message.from_user.full_name,
    )

    already_accepted = await OfferAgreementService.has_accepted(message.from_user.id)

    if already_accepted:
        await _finalize_shop_creation(message, shop, bot_info["username"], state)
        return

    await state.update_data(shop_id=shop["id"], bot_username=bot_info["username"])
    await state.set_state(None)

    await message.answer(
        f"✅ <b>Магазин «{shop['name']}» создан!</b>\n\n"
        "🎁 Для активации бесплатного периода (7 дней) необходимо принять "
        "условия <b>публичной оферты</b> и <b>политики конфиденциальности</b>.\n\n"
        "Ознакомьтесь с документами и нажмите кнопку ниже для активации.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Принять оферту и политику",
                        callback_data=f"accept_offer_trial:{shop['id']}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="📄 Скачать оферту",
                        callback_data="show_offer",
                    ),
                    InlineKeyboardButton(
                        text="🔒 Скачать политику",
                        callback_data="show_privacy",
                    ),
                ],
            ]
        ),
    )


async def _send_shop_links_via_shop_bot(
    shop_id: int, owner_telegram_id: int, bot_username: str | None
) -> None:
    """Отправляет ссылки на админ-панель и мини-приложение через бота магазина."""
    from app.services.admin_auth_service import AdminAuthService

    shop_bot = get_bot(shop_id)
    if shop_bot is None:
        logger.warning("Магазин %d: бот не найден — ссылки не отправлены", shop_id)
        return

    admin_url = settings.admin_panel_url

    login_url = await AdminAuthService.create_login_url(owner_telegram_id, shop_id)
    if login_url is None:
        login_url = f"{admin_url.rstrip('/')}/login" if admin_url else None

    kb_rows = []
    if login_url:
        kb_rows.append([InlineKeyboardButton(text="📊 Открыть админ-панель", url=login_url)])
    if bot_username:
        shop_url = f"https://t.me/{bot_username}?startapp=shop_{shop_id}"
        kb_rows.append([InlineKeyboardButton(text="📱 Мини-приложение", url=shop_url)])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None

    text = "👋 <b>Добро пожаловать в магазин!</b>\n\n"
    if login_url:
        text += "📊 <b>Админ-панель:</b> нажмите кнопку ниже\n\n"
        text += "Ссылка для входа действует 5 минут. "
        "Получить новую — команда /admin в этом боте.\n\n"
    if bot_username:
        text += "📱 <b>Мини-приложение:</b> нажмите кнопку ниже"

    try:
        await shop_bot.send_message(
            chat_id=owner_telegram_id,
            text=text,
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("Магазин %d: не удалось отправить ссылки через бота магазина", shop_id)


async def _finalize_shop_creation(
    message: Message, shop: dict, bot_username: str | None, state: FSMContext
) -> None:
    """Активирует триал, запускает бота магазина и отправляет сообщение об успехе."""
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

    for _ in range(10):
        if get_bot(shop["id"]) is not None:
            break
        await asyncio.sleep(0.5)

    await _send_shop_links_via_shop_bot(
        shop["id"], shop.get("owner_telegram_id"), bot_username
    )

    text = (
        f"🎉 <b>Готово! Ваш магазин работает!</b>\n\n"
        f"🎁 Подписка: 7 дней бесплатно\n\n"
    )
    if bot_username:
        text += (
            f"📊 Ссылки на админ-панель и мини-приложение "
            f"отправлены в боте @{bot_username}.\n\n"
            f"Если не получили — откройте бота @{bot_username} и нажмите /start"
        )
    else:
        text += "📊 Ссылки на админ-панель отправлены в вашем боте."

    await message.answer(text, disable_web_page_preview=True)

    await state.clear()


def _split_text(text: str, max_length: int = 4000) -> list[str]:
    """Разбивает длинный текст на части для отправки в Telegram (лимит 4096)."""
    if len(text) <= max_length:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        split_at = text.rfind("\n\n", 0, max_length)
        if split_at == -1:
            split_at = text.rfind("\n", 0, max_length)
        if split_at == -1:
            split_at = max_length
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


def _make_text_document(text: str, filename: str) -> BufferedInputFile:
    """Создаёт BufferedInputFile из текста для отправки файлом."""
    return BufferedInputFile(text.encode("utf-8"), filename=filename)


async def on_offer(message: Message) -> None:
    """Присылает файл оферты и кнопку принятия."""
    offer_text = get_offer_text()

    if not offer_text:
        await message.answer("Текст оферты временно недоступен.")
        return

    accepted = await OfferAgreementService.has_accepted(message.from_user.id)

    await message.answer_document(
        document=_make_text_document(offer_text, "Публичная_оферта.txt"),
        caption="📄 <b>Публичная оферта</b>\n\nСкачайте файл, чтобы ознакомиться с полным текстом.",
    )

    if accepted:
        await message.answer("✅ <b>Вы уже приняли условия оферты.</b>")
    else:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Принять условия оферты", callback_data="accept_offer")]
            ]
        )
        await message.answer(
            "Ознакомившись с офертой, нажмите кнопку ниже, чтобы принять условия.",
            reply_markup=kb,
        )


async def on_accept_offer(callback: CallbackQuery) -> None:
    """Записывает факт принятия оферты."""
    await OfferAgreementService.accept(
        telegram_user_id=callback.from_user.id,
        full_name=callback.from_user.full_name,
        username=callback.from_user.username,
    )

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "✅ <b>Вы приняли условия публичной оферты.</b>\n\n"
        "Спасибо! Запись о принятии сохранена."
    )
    await callback.answer("Оферта принята")


async def _show_offer_before_payment(callback: CallbackQuery, shop_id: int, plan_id: int) -> None:
    """Показывает краткую оферту с кнопкой принятия перед оплатой."""
    await callback.message.answer(
        "📄 <b>Перед оплатой необходимо принять условия публичной оферты.</b>\n\n"
        "Ознакомьтесь с полным текстом в разделе «📄 Оферта».\n\n"
        "Нажмите кнопку ниже, чтобы принять и продолжить оплату.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Принять условия оферты",
                        callback_data=f"accept_offer_pay:{shop_id}:{plan_id}",
                    ),
                    InlineKeyboardButton(
                        text="📄 Скачать оферту",
                        callback_data="show_offer",
                    ),
                ],
            ]
        ),
    )


async def on_show_offer(callback: CallbackQuery) -> None:
    """Присылает файл оферты (inline-кнопка)."""
    offer_text = get_offer_text()
    if not offer_text:
        await callback.answer("Текст оферты временно недоступен.", show_alert=True)
        return

    accepted = await OfferAgreementService.has_accepted(callback.from_user.id)

    await callback.message.answer_document(
        document=_make_text_document(offer_text, "Публичная_оферта.txt"),
        caption="📄 <b>Публичная оферта</b>\n\nСкачайте файл, чтобы ознакомиться с полным текстом.",
    )

    if accepted:
        await callback.message.answer("✅ <b>Вы уже приняли условия оферты.</b>")
    else:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Принять условия оферты", callback_data="accept_offer")]
            ]
        )
        await callback.message.answer(
            "Ознакомившись с офертой, нажмите кнопку ниже, чтобы принять условия.",
            reply_markup=kb,
        )
    await callback.answer()


async def on_show_privacy(callback: CallbackQuery) -> None:
    """Присылает файл политики конфиденциальности (inline-кнопка)."""
    privacy_text = get_privacy_policy_text()
    if not privacy_text:
        await callback.answer("Текст политики конфиденциальности временно недоступен.", show_alert=True)
        return

    await callback.message.answer_document(
        document=_make_text_document(privacy_text, "Политика_конфиденциальности.txt"),
        caption="🔒 <b>Политика конфиденциальности</b>\n\nСкачайте файл, чтобы ознакомиться с полным текстом.",
    )
    await callback.answer()


async def on_accept_offer_and_trial(callback: CallbackQuery, state: FSMContext) -> None:
    """Принимает оферту + политику и активирует бесплатный период."""
    shop_id = int(callback.data.split(":")[1])

    await OfferAgreementService.accept(
        telegram_user_id=callback.from_user.id,
        full_name=callback.from_user.full_name,
        username=callback.from_user.username,
    )

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "✅ <b>Вы приняли условия оферты и политики конфиденциальности.</b>\n\n"
        "🎁 Активирую бесплатный период..."
    )
    await callback.answer("Оферта и политика приняты")

    data = await state.get_data()
    bot_username = data.get("bot_username")

    shop = await ShopService.get(shop_id)
    if shop is None:
        await callback.message.answer("❌ Магазин не найден. Обратитесь в поддержку.")
        await state.clear()
        return

    if not bot_username:
        bot_info = await _validate_bot_token(shop["bot_token"])
        bot_username = bot_info["username"] if bot_info else None

    await _finalize_shop_creation(callback.message, shop, bot_username, state)


async def _create_and_send_payment(message: Message, shop_id: int, plan_id: int) -> None:
    """Создаёт платёж и отправляет ссылку."""
    result = await SubscriptionPaymentService.create_payment(
        shop_id=shop_id,
        plan_id=plan_id,
    )

    if result is None:
        await message.answer(
            "❌ Не удалось создать платёж. Попробуйте позже или обратитесь к администратору."
        )
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=result["confirmation_url"])],
        ]
    )

    await message.answer(
        "👇 Нажмите кнопку ниже для перехода к оплате.\n\n"
        "После оплаты подписка активируется автоматически.",
        reply_markup=kb,
    )


async def on_support(message: Message) -> None:
    username = settings.support_bot_username
    if username:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💬 Написать в поддержку", url=f"https://t.me/{username}")],
            ]
        )
        await message.answer(
            "🛠 <b>Техническая поддержка</b>\n\n"
            "Нажмите кнопку ниже — откроется чат с нашим ботом поддержки.\n"
            "Мы ответим на любой вопрос: настройка, оплата, баги, фичи.",
            reply_markup=kb,
        )
    else:
        await message.answer(
            "🛠 <b>Техническая поддержка</b>\n\n"
            "Поддержка временно недоступна. Попробуйте позже."
        )


async def on_about(message: Message) -> None:
    text = (
        "🛍 <b>TG Shop — платформа магазинов в Telegram</b>\n\n"

        "📦 <b>Что это?</b>\n"
        "Конструктор, который за 5 минут превращает Telegram-бота\n"
        "в полноценный интернет-магазин: каталог, корзина, оплата,\n"
        "заказы и CRM — всё внутри Telegram.\n\n"

        "👥 <b>Для кого</b>\n"
        "• Малый бизнес и самозанятые\n"
        "• Продавцы свечей, косметики, еды, мерча и не только\n"
        "• Те, кто устал вести продажи через записи в блокноте\n"
        "  и переписки в личке\n\n"

        "✅ <b>Какие проблемы решает</b>\n"
        "• Клиентам больше не нужно писать вам в личку —\n"
        "  они выбирают и заказывают сами в боте\n"
        "• Все заказы, клиенты и товары — в одном месте\n"
        "• Не нужен программист: каталог, категории и цены\n"
        "  настраиваются через удобную админ-панель\n\n"

        "🚀 <b>Преимущества</b>\n"
        "• <b>Запуск за 5 минут</b> — создал бота, добавил товары, продаёшь\n"
        "• <b>Корзина и оформление заказа</b> — клиент сам собирает покупку\n"
        "• <b>Админ-панель</b> на ПК — управляйте магазином с компьютера\n"
        "• <b>CRM</b> — история заказов и база клиентов всегда под рукой\n"
        "• <b>Рассылки</b> — возвращайте клиентов уведомлениями об акциях\n"
        "• <b>Промокоды и отзывы</b> — инструменты для роста продаж\n"
        "• <b>Мини-приложение</b> — красивый каталог прямо в Telegram\n\n"

        "🎁 <b>7 дней бесплатно</b> — попробуйте все возможности без оплаты.\n\n"

        "Готовы начать? Нажмите <b>🚀 Создать магазин</b> в меню 👇"
    )
    await message.answer(text)


async def on_my_shops(message: Message) -> None:
    tg_id = message.from_user.id
    user_shops = await ShopService.get_by_owner(tg_id)

    if not user_shops:
        await message.answer("У вас пока нет магазинов.", reply_markup=_main_menu())
        return

    await message.answer("📋 <b>Ваши магазины:</b>", reply_markup=_main_menu(is_new=False))

    for shop in user_shops:
        await _send_shop_card(message, shop)


async def on_subscription(message: Message) -> None:
    """Показывает статус подписки и доступные тарифы для оплаты."""
    tg_id = message.from_user.id
    user_shops = await ShopService.get_by_owner(tg_id)

    if not user_shops:
        await _show_plans_without_shop(message)
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


async def _show_plans_without_shop(message: Message) -> None:
    """Показывает тарифы подписки пользователю без магазина."""
    plans = await SubscriptionService.get_plans()

    if not plans:
        await message.answer(
            "Тарифы не настроены. Обратитесь к администратору.",
            reply_markup=_main_menu(),
        )
        return

    features = plans[0].get("features", [])

    text = (
        "💳 <b>Подписка</b>\n\n"
        f"{'---' * 10}\n"
        f"📦 <b>Тариф: 5000 ₽ / месяц</b>\n\n"
    )

    for feature in features:
        text += f"  ✅ {feature}\n"

    text += f"\n{'---' * 10}\n"
    text += "<b>Доступные периоды оплаты:</b>\n\n"

    for plan in plans:
        if plan["description"]:
            text += f"🔸 <b>{plan['name']}</b> — {int(plan['price']):,} ₽\n"
            text += f"<i>{plan['description']}</i>\n\n"
        else:
            text += f"🔸 <b>{plan['name']}</b> — {int(plan['price']):,} ₽\n\n"

    text += (
        "🎁 <b>7 дней бесплатно</b> при создании первого магазина.\n\n"
        "Создайте магазин кнопкой «➕ Создать магазин» — триал активируется автоматически."
    )

    await message.answer(text, reply_markup=_main_menu(), disable_web_page_preview=True)


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

        kb_rows.append([
            InlineKeyboardButton(
                text=f"💳 {plan['name']} — {int(plan['price']):,} ₽".replace(",", " "),
                callback_data=f"pay:{shop_id}:{plan['id']}",
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None

    send = message.answer if isinstance(message, Message) else message.message.answer
    await send(text, reply_markup=kb, disable_web_page_preview=True)


async def on_pay(callback: CallbackQuery) -> None:
    """Создаёт платёж через ЮKassa и отправляет ссылку на оплату."""
    _, shop_id_str, plan_id_str = callback.data.split(":")
    shop_id = int(shop_id_str)
    plan_id = int(plan_id_str)

    if not settings.yookassa_enabled:
        await callback.answer("Оплата скоро будет доступна", show_alert=True)
        return

    accepted = await OfferAgreementService.has_accepted(callback.from_user.id)
    if not accepted:
        await callback.answer("Сначала примите условия оферты", show_alert=True)
        await _show_offer_before_payment(callback, shop_id, plan_id)
        return

    await callback.answer("Создаю платёж...")

    await _create_and_send_payment(callback.message, shop_id, plan_id)


async def on_accept_offer_and_pay(callback: CallbackQuery) -> None:
    """Принимает оферту и сразу создаёт платёж."""
    _, shop_id_str, plan_id_str = callback.data.split(":")
    shop_id = int(shop_id_str)
    plan_id = int(plan_id_str)

    await OfferAgreementService.accept(
        telegram_user_id=callback.from_user.id,
        full_name=callback.from_user.full_name,
        username=callback.from_user.username,
    )

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "✅ <b>Вы приняли условия публичной оферты.</b>\n\n"
        "Создаём платёж..."
    )
    await callback.answer("Оферта принята")

    await _create_and_send_payment(callback.message, shop_id, plan_id)


async def on_subscription_shop(callback: CallbackQuery) -> None:
    """Показывает подписку для конкретного магазина (выбор из списка)."""
    shop_id = int(callback.data.split(":")[1])
    shop = await ShopService.get(shop_id)

    if shop is None:
        await callback.answer("Магазин не найден", show_alert=True)
        return

    await _show_subscription_for_shop(callback, shop)


async def on_delete_shop(callback: CallbackQuery) -> None:
    """Показывает подтверждение удаления магазина (только владелец)."""
    shop_id = int(callback.data.split(":")[1])
    shop = await ShopService.get(shop_id)

    if shop is None:
        await callback.answer("Магазин не найден", show_alert=True)
        return

    if shop["owner_telegram_id"] != callback.from_user.id:
        await callback.answer("Это не ваш магазин", show_alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=f"delete_shop_confirm:{shop_id}",
                ),
                InlineKeyboardButton(text="❌ Отмена", callback_data="delete_shop_cancel"),
            ]
        ]
    )
    await callback.message.answer(
        f"⚠️ <b>Удалить магазин «{shop['name']}»?</b>\n\n"
        "Будут удалены все товары, заказы, клиенты и настройки.\n"
        "Это действие <b>нельзя отменить</b>.",
        reply_markup=kb,
    )
    await callback.answer()


async def on_delete_shop_confirm(callback: CallbackQuery) -> None:
    """Удаляет магазин после подтверждения (только владелец)."""
    shop_id = int(callback.data.split(":")[1])
    shop = await ShopService.get(shop_id)

    if shop is None:
        await callback.answer("Магазин не найден", show_alert=True)
        return

    if shop["owner_telegram_id"] != callback.from_user.id:
        await callback.answer("Это не ваш магазин", show_alert=True)
        return

    shop_name = shop["name"]
    try:
        await stop_shop_bot(shop_id)
    except Exception:
        logger.exception("Не удалось остановить бота магазина %d при удалении", shop_id)

    await ShopService.delete(shop_id)

    await callback.message.edit_text(
        f"✅ Магазин «{shop_name}» удалён.",
        reply_markup=None,
    )
    await callback.answer("Магазин удалён")


async def on_delete_shop_cancel(callback: CallbackQuery) -> None:
    """Отмена удаления магазина."""
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Удаление отменено")


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
    dp.message.register(on_support, F.text == "🛠 Поддержка")
    dp.message.register(on_about, F.text == "ℹ️ О платформе")
    dp.message.register(on_offer, F.text == "📄 Оферта")
    dp.callback_query.register(on_accept_offer, F.data == "accept_offer")
    dp.callback_query.register(on_show_offer, F.data == "show_offer")
    dp.callback_query.register(on_show_privacy, F.data == "show_privacy")
    dp.callback_query.register(
        on_accept_offer_and_pay, F.data.startswith("accept_offer_pay:")
    )
    dp.callback_query.register(
        on_accept_offer_and_trial, F.data.startswith("accept_offer_trial:")
    )
    dp.callback_query.register(on_enter_token, F.data == "enter_token")
    dp.callback_query.register(
        on_subscription_shop, F.data.startswith("sub_shop:")
    )
    dp.callback_query.register(on_pay, F.data.startswith("pay:"))
    dp.callback_query.register(on_delete_shop, F.data.startswith("delete_shop:"))
    dp.callback_query.register(
        on_delete_shop_confirm, F.data.startswith("delete_shop_confirm:")
    )
    dp.callback_query.register(on_delete_shop_cancel, F.data == "delete_shop_cancel")
    dp.message.register(on_token_received, StateFilter(OnboardingStates.waiting_for_token))
    dp.message.register(on_name_received, StateFilter(OnboardingStates.waiting_for_name))

    return dp
