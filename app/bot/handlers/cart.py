from aiogram import Router, F
from app.bot.shop_context import get_shop_id
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.cart import get_cart_keyboard
from app.bot.utils.messages import show_screen, replace_with_text
from app.core.config import settings
from app.services.cart_service import CartService
from app.services.legal_document_service import LegalDocumentService
from app.services.message_service import MessageService
from app.services.shop_service import ShopService


def setup_router() -> Router:
    router = Router()

    def _split_text(text: str, max_length: int = 4000) -> list[str]:
        """Разбивает длинный текст на части для отправки в Telegram."""
        return [text[i:i + max_length] for i in range(0, len(text), max_length)]

    def _make_text_document(text: str, filename: str) -> BufferedInputFile:
        """Создаёт BufferedInputFile из текста для отправки файлом."""
        return BufferedInputFile(text.encode("utf-8"), filename=filename)

    async def _render_cart_text(items: list[dict]) -> str:
        if not items:
            return await MessageService.get(get_shop_id(), "cart_empty")

        lines = ["🛒 <b>Ваша корзина</b>\n"]

        total = 0

        for item in items:
            lines.append(
                f"{item['product_name']} ({item['volume']}) "
                f"— {item['price']} ₽ × {item['quantity']} = {item['subtotal']} ₽"
            )
            total += item["subtotal"]

        lines.append(f"\n💰 Итого: <b>{total} ₽</b>")

        return "\n".join(lines)

    async def _render_cart_cb(callback: CallbackQuery, state: FSMContext) -> None:
        items = await CartService.get_items(get_shop_id(), callback.from_user.id)

        await replace_with_text(
            callback.message,
            callback.bot,
            callback.message.chat.id,
            state,
            await _render_cart_text(items),
            reply_markup=get_cart_keyboard(items),
        )

        await callback.answer()

    @router.message(F.text == "🛒 Корзина")
    async def open_cart_msg(message: Message, state: FSMContext):
        await state.clear()

        items = await CartService.get_items(get_shop_id(), message.from_user.id)

        await show_screen(
            message,
            state,
            await _render_cart_text(items),
            reply_markup=get_cart_keyboard(items),
        )

    @router.callback_query(F.data == "cart")
    async def open_cart_cb(callback: CallbackQuery, state: FSMContext):
        await _render_cart_cb(callback, state)

    @router.callback_query(F.data.startswith("cart_inc:"))
    async def increase_quantity(callback: CallbackQuery):
        cart_item_id = int(callback.data.split(":")[1])

        await CartService.change_quantity(get_shop_id(), callback.from_user.id, cart_item_id, +1)

        items = await CartService.get_items(get_shop_id(), callback.from_user.id)

        await callback.message.edit_text(
            await _render_cart_text(items),
            reply_markup=get_cart_keyboard(items)
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("cart_dec:"))
    async def decrease_quantity(callback: CallbackQuery):
        cart_item_id = int(callback.data.split(":")[1])

        await CartService.change_quantity(get_shop_id(), callback.from_user.id, cart_item_id, -1)

        items = await CartService.get_items(get_shop_id(), callback.from_user.id)

        await callback.message.edit_text(
            await _render_cart_text(items),
            reply_markup=get_cart_keyboard(items)
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("cart_remove:"))
    async def remove_item(callback: CallbackQuery):
        cart_item_id = int(callback.data.split(":")[1])

        await CartService.remove_item(get_shop_id(), callback.from_user.id, cart_item_id)

        items = await CartService.get_items(get_shop_id(), callback.from_user.id)

        await callback.message.edit_text(
            await _render_cart_text(items),
            reply_markup=get_cart_keyboard(items)
        )
        await callback.answer()

    @router.callback_query(F.data == "checkout")
    async def checkout(callback: CallbackQuery, state: FSMContext):
        shop_id = get_shop_id()

        unavailable = await CartService.check_availability(shop_id, callback.from_user.id)

        if unavailable:
            lines = ["⚠️ <b>Не хватает товара:</b>\n"]
            for item in unavailable:
                if item["available"] == 0:
                    lines.append(
                        f"• {item['product_name']} ({item['volume']}) — закончился"
                    )
                else:
                    lines.append(
                        f"• {item['product_name']} ({item['volume']}) — "
                        f"на складе {item['available']} шт."
                    )
            lines.append("\nУменьшите количество в корзине.")

            items = await CartService.get_items(shop_id, callback.from_user.id)

            await callback.message.edit_text(
                "\n".join(lines),
                reply_markup=get_cart_keyboard(items),
            )
            await callback.answer()
            return

        shop = await ShopService.get(shop_id)

        if shop and shop.get("offer_text"):
            accepted = await ShopService.has_accepted_offer(shop_id, callback.from_user.id)
            if not accepted:
                builder = InlineKeyboardBuilder()
                builder.button(text="✅ Принять условия", callback_data="accept_shop_offer")
                builder.button(text="📄 Скачать оферту", callback_data="show_shop_offer")
                builder.adjust(1)

                await callback.message.edit_text(
                    "📋 Перед оформлением заказа необходимо принять условия оферты магазина.",
                    reply_markup=builder.as_markup(),
                )
                await callback.answer()
                return

        if not await _check_customer_consent(callback, shop_id):
            return

        await _show_checkout_webapp(callback, shop_id)

    async def _check_customer_consent(callback: CallbackQuery, shop_id: int) -> bool:
        """Показывает согласие на обработку ПДн перед оформлением заказа.

        Возвращает True, если можно продолжать к webapp.
        """
        consent_text = await LegalDocumentService.get_customer_consent_text(shop_id)
        if not consent_text:
            return True

        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Согласен и продолжить", callback_data="accept_customer_consent")
        builder.button(text="📄 Скачать документ", callback_data="show_customer_consent")
        builder.button(text="⬅ Назад", callback_data="cart")
        builder.adjust(1)

        await callback.message.edit_text(
            "📋 <b>Согласие на обработку персональных данных</b>\n\n"
            "Перед вводом контактных данных ознакомьтесь с условиями\n"
            "обработки персональных данных. Нажмите «Согласен», чтобы продолжить.",
            reply_markup=builder.as_markup(),
        )
        await callback.answer()
        return False

    @router.callback_query(F.data == "show_customer_consent")
    async def show_customer_consent(callback: CallbackQuery):
        """Присылает файл согласия на обработку ПДн."""
        shop_id = get_shop_id()
        text = await LegalDocumentService.get_customer_consent_text(shop_id)

        if not text:
            await callback.answer("Текст согласия недоступен", show_alert=True)
            return

        await callback.message.answer_document(
            document=_make_text_document(text, "Согласие_на_обработку_ПДн.txt"),
            caption="📋 <b>Согласие на обработку персональных данных</b>\n\n"
                    "Скачайте файл, чтобы ознакомиться с полным текстом.",
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Согласен и продолжить", callback_data="accept_customer_consent")],
                [InlineKeyboardButton(text="⬅ Назад", callback_data="accept_customer_consent")],
            ]
        )
        await callback.message.answer(
            "Ознакомившись с документом, нажмите кнопку ниже.",
            reply_markup=kb,
        )
        await callback.answer()

    @router.callback_query(F.data == "accept_customer_consent")
    async def accept_customer_consent(callback: CallbackQuery):
        """Перенаправляет к оформлению после показа согласия."""
        shop_id = get_shop_id()
        await _show_checkout_webapp(callback, shop_id)

    async def _show_checkout_webapp(callback: CallbackQuery, shop_id: int):
        """Показывает кнопку мини-приложения для оформления заказа."""
        if settings.webapp_enabled:
            webapp_url = f"{settings.webapp_url}?shop={shop_id}"
            builder = InlineKeyboardBuilder()
            builder.button(text="📝 Перейти к оформлению", web_app=WebAppInfo(url=webapp_url))
            builder.button(text="⬅ Назад", callback_data="cart")
            builder.adjust(1)

            await callback.message.edit_text(
                "Отлично! Нажмите кнопку ниже, чтобы оформить заказ.",
                reply_markup=builder.as_markup(),
            )
        else:
            await callback.message.edit_text(
                "📝 Оформление заказа пока недоступно. Свяжитесь с менеджером.",
            )

        await callback.answer()

    @router.callback_query(F.data == "show_shop_offer")
    async def show_shop_offer(callback: CallbackQuery):
        """Присылает файл оферты магазина."""
        shop_id = get_shop_id()
        shop = await ShopService.get(shop_id)
        text = shop.get("offer_text", "") if shop else ""

        if not text:
            await callback.answer("Текст оферты недоступен", show_alert=True)
            return

        accepted = await ShopService.has_accepted_offer(shop_id, callback.from_user.id)

        await callback.message.answer_document(
            document=_make_text_document(text, "Оферта_магазина.txt"),
            caption="📄 <b>Оферта магазина</b>\n\nСкачайте файл, чтобы ознакомиться с полным текстом.",
        )

        if accepted:
            await callback.message.answer(
                "✅ <b>Вы уже приняли условия оферты.</b>",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="⬅ Назад", callback_data="checkout")],
                    ]
                ),
            )
        else:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Принять условия", callback_data="accept_shop_offer")],
                    [InlineKeyboardButton(text="⬅ Назад", callback_data="checkout")],
                ]
            )
            await callback.message.answer(
                "Ознакомившись с офертой, нажмите кнопку ниже, чтобы принять условия.",
                reply_markup=kb,
            )
        await callback.answer()

    @router.callback_query(F.data == "accept_shop_offer")
    async def accept_shop_offer(callback: CallbackQuery):
        """Записывает принятие оферты магазина и показывает кнопку оформления."""
        shop_id = get_shop_id()

        await ShopService.accept_offer(
            shop_id=shop_id,
            telegram_user_id=callback.from_user.id,
            full_name=callback.from_user.full_name,
            username=callback.from_user.username,
        )

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ <b>Условия оферты приняты.</b>")
        await callback.answer("Оферта принята")

        if not await _check_customer_consent(callback, shop_id):
            return

        await _show_checkout_webapp(callback, shop_id)

    return router
