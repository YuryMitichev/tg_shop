from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.views.product_view import show_product
from app.bot.states.order import ReviewState
from app.services.catalog_service import CatalogService
from app.services.cart_service import CartService
from app.services.order_service import OrderService
from app.services.review_service import ReviewService

router = Router()


def _rating_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()

    for i in range(1, 6):
        builder.button(text="⭐" * i, callback_data=f"rate:{i}")

    builder.button(text="⬅ Отмена", callback_data="review_cancel")
    builder.adjust(5, 1)

    return builder


@router.callback_query(F.data.startswith("variant:"))
async def select_variant(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Переключение объёма/варианта на карточке товара."""

    variant_id = int(callback.data.split(":")[1])

    data = await state.get_data()

    product_id = data.get("product_id")

    if not product_id:
        await callback.answer("Товар не найден, откройте каталог заново.", show_alert=True)
        return

    product = await CatalogService.get_product(product_id)

    if product is None:
        await callback.answer("Товар больше не найден.", show_alert=True)
        return

    await show_product(
        callback,
        state,
        product,
        variant_id=variant_id,
    )


@router.callback_query(F.data == "add_to_cart")
async def add_to_cart(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Добавление текущего товара (с выбранным вариантом) в корзину."""

    data = await state.get_data()

    product_id = data.get("product_id")
    variant_id = data.get("variant_id")

    if not product_id or not variant_id:
        await callback.answer("Сначала выберите товар.", show_alert=True)
        return

    await CartService.add_item(
        telegram_user_id=callback.from_user.id,
        product_id=product_id,
        variant_id=variant_id,
        quantity=1,
    )

    await callback.answer("Добавлено в корзину ✅")


@router.callback_query(F.data == "review")
async def start_review(callback: CallbackQuery, state: FSMContext):
    """Начало отзыва — только для покупателей товара."""
    data = await state.get_data()
    product_id = data.get("product_id")

    if not product_id:
        await callback.answer("Товар не найден, откройте каталог заново.", show_alert=True)
        return

    has_bought = await OrderService.has_purchased(callback.from_user.id, product_id)

    if not has_bought:
        await callback.answer(
            "⭐ Отзывы доступны только после покупки товара.",
            show_alert=True,
        )
        return

    await state.set_state(ReviewState.waiting_rating)

    await callback.message.answer(
        "⭐ <b>Оцените товар</b>\n\nВыберите оценку:",
        reply_markup=_rating_keyboard().as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rate:"), ReviewState.waiting_rating)
async def process_rating(callback: CallbackQuery, state: FSMContext):
    """Сохранение оценки, запрос текста."""
    rating = int(callback.data.split(":")[1])

    if rating < 1 or rating > 5:
        await callback.answer("Неверная оценка.", show_alert=True)
        return

    await state.update_data(review_rating=rating)
    await state.set_state(ReviewState.waiting_text)

    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Без текста", callback_data="review_no_text")
    builder.button(text="⬅ Отмена", callback_data="review_cancel")

    await callback.message.answer(
        f"Оценка: {'⭐' * rating}\n\n"
        "✍️ Напишите отзыв текстом.\n"
        "Или нажмите «Без текста».",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "review_no_text", ReviewState.waiting_text)
async def save_review_no_text(callback: CallbackQuery, state: FSMContext):
    """Сохранение отзыва без текста."""
    await _save_review(callback, state, text=None)


@router.message(ReviewState.waiting_text, F.text)
async def save_review_text(message: Message, state: FSMContext):
    """Сохранение отзыва с текстом."""
    text = message.text.strip()

    if len(text) > 500:
        await message.answer("❌ Отзыв слишком длинный (до 500 символов).")
        return

    await _save_review(message, state, text=text)


async def _save_review(event: CallbackQuery | Message, state: FSMContext, text: str | None):
    """Общее сохранение отзыва и возврат к карточке товара."""
    data = await state.get_data()

    product_id = data.get("product_id")
    rating = data.get("review_rating")

    if not product_id or not rating:
        await _back_to_product(event, state)
        return

    await ReviewService.create_or_update(
        product_id=product_id,
        telegram_user_id=event.from_user.id,
        rating=rating,
        text=text,
    )

    await state.set_state(None)

    if isinstance(event, CallbackQuery):
        await event.answer("✅ Отзыв сохранён!")
        await _back_to_product(event, state)
    else:
        await event.answer("✅ Отзыв сохранён!")
        await _back_to_product(event, state)


async def _back_to_product(event: CallbackQuery | Message, state: FSMContext):
    """Возврат к карточке товара после отзыва."""
    data = await state.get_data()
    product_id = data.get("product_id")

    if not product_id:
        return

    product = await CatalogService.get_product(product_id)
    if product is None:
        return

    variant_id = data.get("variant_id")

    class _FakeCallback:
        """Заглушка для show_product — работает и с Message, и с CallbackQuery."""
        def __init__(self, ev):
            self.message = ev.message if isinstance(ev, CallbackQuery) else ev
            self.bot = ev.bot
            self.from_user = ev.from_user

        async def answer(self, *args, **kwargs):
            pass

    await show_product(_FakeCallback(event), state, product, variant_id=variant_id)


@router.callback_query(F.data == "review_cancel")
async def cancel_review(callback: CallbackQuery, state: FSMContext):
    """Отмена отзыва, возврат к карточке."""
    await state.set_state(None)

    data = await state.get_data()
    product_id = data.get("product_id")

    if not product_id:
        await callback.answer()
        return

    product = await CatalogService.get_product(product_id)
    if product is None:
        await callback.answer()
        return

    variant_id = data.get("variant_id")
    await show_product(_FakeCallback(callback), state, product, variant_id=variant_id)
    await callback.answer("Отменено")
