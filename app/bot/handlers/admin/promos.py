from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.filters.admin import IsAdmin
from app.bot.keyboards.admin import (
    get_admin_promo_detail_keyboard,
    get_admin_promos_keyboard,
)
from app.bot.shop_context import get_shop_id
from app.bot.states.admin_product import AdminPromoState
from app.services.promo_service import PromoCodeService


def setup_promos_router() -> Router:
    router = Router()
    router.message.filter(IsAdmin())
    router.callback_query.filter(IsAdmin())

    @router.callback_query(F.data == "admin_promos")
    async def list_promos(callback: CallbackQuery, state: FSMContext):
        await state.clear()

        promos = await PromoCodeService.get_all(get_shop_id())

        await callback.message.edit_text(
            "🎟 <b>Промокоды</b>\n\n"
            "✅ — активен, 🚫 — выключен",
            reply_markup=get_admin_promos_keyboard(promos),
        )

        await callback.answer()

    @router.callback_query(F.data.startswith("admin_promo:"))
    async def show_promo_detail(callback: CallbackQuery):
        promo_id = int(callback.data.split(":")[1])

        promos = await PromoCodeService.get_all(get_shop_id())
        promo = next((p for p in promos if p["id"] == promo_id), None)

        if promo is None:
            await callback.answer("Промокод не найден.", show_alert=True)
            return

        if promo["discount_type"] == "percent":
            val = f"−{promo['discount_value']}%"
        else:
            val = f"−{promo['discount_value']} ₽"

        uses = f"{promo['used_count']}/{promo['max_uses']}" if promo["max_uses"] else f"{promo['used_count']}/∞"
        status = "✅ Активен" if promo["is_active"] else "🚫 Выключен"

        await callback.message.edit_text(
            f"🎟 <b>Промокод {promo['code']}</b>\n\n"
            f"Скидка: {val}\n"
            f"Использовано: {uses}\n"
            f"Статус: {status}",
            reply_markup=get_admin_promo_detail_keyboard(promo_id, promo["is_active"]),
        )

        await callback.answer()

    @router.callback_query(F.data == "admin_promo_new")
    async def create_promo_start(callback: CallbackQuery, state: FSMContext):
        await state.set_state(AdminPromoState.waiting_code)

        await callback.message.edit_text(
            "🎟 <b>Создание промокода</b>\n\n"
            "Шаг 1/4: введите код промокода (например: <code>NEW10</code>):",
        )

        await callback.answer()

    @router.message(AdminPromoState.waiting_code)
    async def create_promo_code(message: Message, state: FSMContext):
        code = message.text.strip().upper()

        if len(code) < 3 or len(code) > 20:
            await message.answer("Код должен быть 3–20 символов. Попробуйте ещё раз.")
            return

        await state.update_data(code=code)
        await state.set_state(AdminPromoState.waiting_type)

        builder = InlineKeyboardBuilder()
        builder.button(text="Процент (%)", callback_data="promo_type:percent")
        builder.button(text="Фиксированная сумма (₽)", callback_data="promo_type:fixed")
        builder.adjust(1)

        await message.answer(
            "Шаг 2/4: выберите тип скидки:",
            reply_markup=builder.as_markup(),
        )

    @router.callback_query(F.data.startswith("promo_type:"), AdminPromoState.waiting_type)
    async def create_promo_type(callback: CallbackQuery, state: FSMContext):
        discount_type = callback.data.split(":")[1]

        await state.update_data(discount_type=discount_type)
        await state.set_state(AdminPromoState.waiting_value)

        unit = "%" if discount_type == "percent" else " ₽"
        await callback.message.edit_text(
            f"Шаг 3/4: введите размер скидки в {unit}:\n"
            "(для процента — число от 1 до 100)",
        )

        await callback.answer()

    @router.message(AdminPromoState.waiting_value)
    async def create_promo_value(message: Message, state: FSMContext):
        text = message.text.strip()

        if not text.isdigit():
            await message.answer("Введите число.")
            return

        value = int(text)

        data = await state.get_data()

        if data["discount_type"] == "percent" and (value < 1 or value > 100):
            await message.answer("Проент должен быть от 1 до 100. Попробуйте ещё раз.")
            return

        if value < 1:
            await message.answer("Сумма должна быть больше 0. Попробуйте ещё раз.")
            return

        await state.update_data(discount_value=value)
        await state.set_state(AdminPromoState.waiting_max_uses)

        builder = InlineKeyboardBuilder()
        builder.button(text="♾ Без лимита", callback_data="promo_uses:unlimited")

        await message.answer(
            "Шаг 4/4: введите максимальное количество использований,\n"
            "или нажмите «Без лимита»:",
            reply_markup=builder.as_markup(),
        )

    @router.callback_query(F.data == "promo_uses:unlimited", AdminPromoState.waiting_max_uses)
    async def create_promo_unlimited(callback: CallbackQuery, state: FSMContext):
        await _finish_promo_creation(callback, state, max_uses=None)

    @router.message(AdminPromoState.waiting_max_uses)
    async def create_promo_max_uses(message: Message, state: FSMContext):
        text = message.text.strip()

        if not text.isdigit():
            await message.answer("Введите число.")
            return

        await _finish_promo_creation(message, state, max_uses=int(text))

    async def _finish_promo_creation(event, state: FSMContext, max_uses: int | None):
        data = await state.get_data()
        await state.clear()

        promo_id = await PromoCodeService.create(get_shop_id(),
            code=data["code"],
            discount_type=data["discount_type"],
            discount_value=data["discount_value"],
            max_uses=max_uses,
        )

        unit = "%" if data["discount_type"] == "percent" else " ₽"
        uses_str = str(max_uses) if max_uses else "∞"

        promos = await PromoCodeService.get_all(get_shop_id())

        msg = event.message if isinstance(event, CallbackQuery) else event

        await msg.answer(
            f"✅ Промокод <b>{data['code']}</b> создан!\n\n"
            f"Скидка: −{data['discount_value']}{unit}\n"
            f"Лимит: {uses_str} использований",
            reply_markup=get_admin_promos_keyboard(promos),
        )

    @router.callback_query(F.data.startswith("admin_promo_toggle:"))
    async def toggle_promo(callback: CallbackQuery):
        promo_id = int(callback.data.split(":")[1])

        await PromoCodeService.toggle_active(get_shop_id(), promo_id)

        promos = await PromoCodeService.get_all(get_shop_id())

        await callback.message.edit_text(
            "🎟 <b>Промокоды</b>\n\n"
            "✅ — активен, 🚫 — выключен",
            reply_markup=get_admin_promos_keyboard(promos),
        )

        await callback.answer("Статус изменён")

    @router.callback_query(F.data.startswith("admin_promo_delete:"))
    async def delete_promo(callback: CallbackQuery):
        promo_id = int(callback.data.split(":")[1])

        await PromoCodeService.delete(get_shop_id(), promo_id)

        promos = await PromoCodeService.get_all(get_shop_id())

        await callback.message.edit_text(
            "✅ Промокод удалён.\n\n"
            "🎟 <b>Промокоды</b>\n\n"
            "✅ — активен, 🚫 — выключен",
            reply_markup=get_admin_promos_keyboard(promos),
        )

        await callback.answer("Удалён")

    return router
