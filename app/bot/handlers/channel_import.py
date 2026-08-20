from __future__ import annotations

import asyncio
from collections import defaultdict

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    KeyboardButtonRequestChat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from sqlalchemy import select

from app.bot.shop_context import get_shop_id
from app.database.db import async_session
from app.models.channel_import import ChannelConnection
from app.models.shop import Shop
from app.services.channel_import_service import ChannelImportService
from app.services.channel_post_button_service import ChannelPostButtonService
from app.services.channel_storefront_service import ChannelStorefrontService
from app.utils.escape import esc


_album_messages: defaultdict[tuple[int, str], list[tuple[Message, bool]]] = defaultdict(list)
_album_tasks: dict[tuple[int, str], asyncio.Task] = {}


class ChannelImportState(StatesGroup):
    waiting_stock = State()
    waiting_product_search = State()


def _next_missing_stock(variants: list[dict], start: int = 0) -> int | None:
    return next(
        (index for index in range(start, len(variants)) if variants[index].get("stock") is None),
        None,
    )


def _stock_prompt(variant: dict, index: int, total: int) -> str:
    title = variant.get("title") or variant.get("volume") or "—"
    suffix = f" ({index + 1}/{total})" if total > 1 else ""
    return (
        f"Укажите остаток товара{suffix} для варианта «{esc(title)}» — "
        "целое число от 0. Для отмены отправьте «отмена»."
    )


async def _owner_shop(shop_id: int, telegram_id: int) -> Shop | None:
    async with async_session() as session:
        return (
            await session.execute(
                select(Shop).where(Shop.id == shop_id, Shop.owner_telegram_id == telegram_id)
            )
        ).scalar_one_or_none()


def _manage_links_markup(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 Настроить товары",
                    callback_data=f"cil:show:{post_id}",
                )
            ]
        ]
    )


def _links_markup(post_id: int, links: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for link in links:
        name = str(link["product_name"])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {name[:32]}",
                    callback_data=f"cil:replace:{post_id}:{link['id']}",
                ),
                InlineKeyboardButton(
                    text="Убрать",
                    callback_data=f"cil:remove:{post_id}:{link['id']}",
                ),
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton(text="➕ Добавить товар", callback_data=f"cil:add:{post_id}")],
            [InlineKeyboardButton(text="🔄 Повторить установку", callback_data=f"cil:retry:{post_id}")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_links(message: Message, shop_id: int, post_id: int) -> None:
    data = await ChannelPostButtonService.list_links(shop_id, post_id)
    links = data["links"]
    sync = data.get("sync") or {}
    link_lines = [
        f"• #{item['product_id']} {esc(item['product_name'])}"
        + (" (выключен)" if not item["is_active"] else "")
        for item in links
    ]
    status = esc(sync.get("status") or "ещё не запускалась")
    error = f"\nОшибка: {esc(sync['last_error'])}" if sync.get("last_error") else ""
    await message.answer(
        "<b>Товары под публикацией</b>\n\n"
        + ("\n".join(link_lines) if link_lines else "Товары пока не прикреплены")
        + f"\n\nСинхронизация: <code>{status}</code>{error}",
        reply_markup=_links_markup(post_id, links),
    )


def _photo_data(message: Message) -> list[dict]:
    if not message.photo:
        return []
    photo = message.photo[-1]
    return [
        {
            "file_id": photo.file_id,
            "file_unique_id": photo.file_unique_id,
            "media_type": "photo",
        }
    ]


async def _ingest_messages(shop_id: int, messages: list[tuple[Message, bool]]) -> None:
    ordered = sorted(messages, key=lambda pair: pair[0].message_id)
    root = ordered[0][0]
    text = next((item.caption or item.text for item, _ in ordered if item.caption or item.text), None)
    media = [photo for item, _ in ordered for photo in _photo_data(item)]
    edited = any(is_edited for _, is_edited in ordered)
    media_payload = None if edited and root.media_group_id and len(ordered) == 1 else media
    reply_markup = next(
        (item.reply_markup for item, _ in ordered if item.reply_markup is not None),
        None,
    )
    reply_markup_known = not (
        edited and root.media_group_id and len(ordered) == 1 and reply_markup is None
    )
    await ChannelImportService.ingest_post(
        shop_id,
        telegram_message_id=root.message_id,
        text=text,
        media=media_payload,
        media_group_id=root.media_group_id,
        published_at=root.date.replace(tzinfo=None) if root.date else None,
        edited_at=(root.edit_date or root.date).replace(tzinfo=None) if edited else None,
        raw_data={
            "source": "bot_api",
            "message_ids": [message.message_id for message, _ in ordered],
            "edited": edited,
            "reply_markup_known": reply_markup_known,
            "reply_markup": (
                reply_markup.model_dump(mode="json", exclude_none=True)
                if reply_markup
                else None
            ),
        },
    )


async def _flush_album(key: tuple[int, str]) -> None:
    await asyncio.sleep(3)
    messages = _album_messages.pop(key, [])
    _album_tasks.pop(key, None)
    if messages:
        await _ingest_messages(key[0], messages)


def setup_router() -> Router:
    router = Router(name="channel_import")

    @router.message(Command("connect_channel"))
    async def connect_channel_command(message: Message):
        if not message.from_user:
            return
        shop_id = get_shop_id()
        if not ChannelImportService.enabled_for_shop(shop_id):
            await message.answer("AI-импорт пока не включён для этого магазина.")
            return
        if await _owner_shop(shop_id, message.from_user.id) is None:
            await message.answer("Подключить канал может только владелец магазина.")
            return
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text="Выбрать канал",
                        request_chat=KeyboardButtonRequestChat(
                            request_id=shop_id,
                            chat_is_channel=True,
                            bot_is_member=True,
                        ),
                    )
                ]
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.answer(
            "Выберите канал, где бот магазина добавлен администратором.",
            reply_markup=keyboard,
        )

    @router.message(Command("pin_store"))
    async def pin_store_command(message: Message, bot: Bot):
        if not message.from_user:
            return
        shop_id = get_shop_id()
        if await _owner_shop(shop_id, message.from_user.id) is None:
            await message.answer("Закрепить магазин может только владелец.")
            return
        try:
            result = await ChannelStorefrontService.sync(shop_id, bot=bot)
        except (ValueError, RuntimeError) as exc:
            await message.answer(f"Не удалось закрепить магазин: {exc}")
            return
        await message.answer(
            "Закреплённая кнопка магазина установлена."
            if result["status"] == "active"
            else "Установка закрепления запущена."
        )

    @router.message(F.chat_shared)
    async def channel_shared(message: Message, bot: Bot):
        if not message.from_user or not message.chat_shared:
            return
        shop_id = get_shop_id()
        if message.chat_shared.request_id != shop_id:
            return
        if await _owner_shop(shop_id, message.from_user.id) is None:
            await message.answer("Подключить канал может только владелец магазина.")
            return
        channel_id = message.chat_shared.chat_id
        bot_user = await bot.get_me()
        try:
            member = await bot.get_chat_member(channel_id, bot_user.id)
            if member.status not in {"administrator", "creator"}:
                raise ValueError
            from app.services.channel_post_button_service import ChannelPostButtonService

            if (
                ChannelPostButtonService.enabled_for_shop(shop_id)
                and member.status == "administrator"
                and not getattr(member, "can_edit_messages", False)
            ):
                await message.answer(
                    "Разрешите боту редактировать публикации канала, чтобы он мог "
                    "добавлять кнопки товаров.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                return
        except Exception:
            await message.answer(
                "Сначала добавьте бота администратором канала и повторите подключение.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        chat = await bot.get_chat(channel_id)
        try:
            connection = await ChannelImportService.connect_channel(
                shop_id,
                channel_id=channel_id,
                channel_title=message.chat_shared.title or chat.title or "Telegram-канал",
                channel_username=message.chat_shared.username or chat.username,
                connected_by=message.from_user.id,
            )
        except ValueError as exc:
            await message.answer(str(exc), reply_markup=ReplyKeyboardRemove())
            return
        if ChannelImportService.mtproto_configured():
            await message.answer(
                "Канал подключён. Запускаю импорт последних 50 публикаций; "
                "новые посты будут поступать в реальном времени.",
                reply_markup=ReplyKeyboardRemove(),
            )
        else:
            await message.answer(
                "Канал подключён в режиме realtime. Новые публикации будут "
                "обрабатываться автоматически. Импорт старых постов пока отключён.",
                reply_markup=ReplyKeyboardRemove(),
            )
        async def start_backfill():
            try:
                await ChannelImportService.enqueue_backfill(shop_id)
            except Exception as exc:
                await message.answer(f"Канал подключён, но backfill не запущен: {exc}")

        if ChannelImportService.mtproto_configured():
            asyncio.create_task(start_backfill())

        async def sync_storefront():
            try:
                await ChannelStorefrontService.sync(shop_id, bot=bot)
                await message.answer("Закреплённая кнопка магазина установлена в канале.")
            except (ValueError, RuntimeError) as exc:
                await message.answer(
                    "Канал подключён, но кнопку магазина закрепить не удалось: "
                    f"{exc}. Повторите командой /pin_store."
                )

        if ChannelStorefrontService.enabled_for_shop(shop_id):
            asyncio.create_task(sync_storefront())

    async def handle_channel_post(message: Message, *, edited: bool) -> None:
        shop_id = get_shop_id()
        if not ChannelImportService.enabled_for_shop(shop_id):
            return
        async with async_session() as session:
            connection = (
                await session.execute(
                    select(ChannelConnection).where(
                        ChannelConnection.shop_id == shop_id,
                        ChannelConnection.channel_id == message.chat.id,
                        ChannelConnection.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
        if connection is None:
            return
        if message.media_group_id:
            key = (shop_id, message.media_group_id)
            _album_messages[key].append((message, edited))
            if key not in _album_tasks:
                _album_tasks[key] = asyncio.create_task(_flush_album(key))
            return
        await _ingest_messages(shop_id, [(message, edited)])

    @router.channel_post()
    async def new_channel_post(message: Message):
        await handle_channel_post(message, edited=False)

    @router.edited_channel_post()
    async def edited_channel_post(message: Message):
        await handle_channel_post(message, edited=True)

    @router.callback_query(F.data.startswith("ci:"))
    async def candidate_action(callback: CallbackQuery, state: FSMContext):
        if not callback.from_user or not callback.data:
            return
        shop_id = get_shop_id()
        if await _owner_shop(shop_id, callback.from_user.id) is None:
            await callback.answer("Доступно только владельцу", show_alert=True)
            return
        _, action, raw_id = callback.data.split(":", 2)
        candidate_id = int(raw_id)
        if action == "links":
            if callback.message:
                await _send_links(callback.message, shop_id, candidate_id)
            await callback.answer()
            return
        post_id: int | None = None
        try:
            if action == "approve":
                candidate = await ChannelImportService.get_candidate(shop_id, candidate_id)
                if candidate is None:
                    raise ValueError("Черновик не найден")
                variants = candidate.get("variants") or []
                missing_index = _next_missing_stock(variants)
                if missing_index is not None:
                    await state.set_state(ChannelImportState.waiting_stock)
                    await state.set_data(
                        {"candidate_id": candidate_id, "variant_index": missing_index}
                    )
                    if callback.message:
                        await callback.message.answer(
                            _stock_prompt(
                                variants[missing_index], missing_index, len(variants)
                            )
                        )
                    await callback.answer()
                    return
                product_id = await ChannelImportService.approve_candidate(
                    shop_id, candidate_id
                )
                post_id = candidate["post"]["id"]
                text = f"Товар опубликован, ID {product_id}."
            elif action == "reject":
                await ChannelImportService.set_candidate_status(
                    shop_id, candidate_id, "rejected", "non_product"
                )
                text = "Черновик отмечен как нетоварный."
            elif action == "duplicate":
                await ChannelImportService.set_candidate_status(
                    shop_id, candidate_id, "duplicate_skipped", "duplicate"
                )
                text = "Черновик отмечен как дубликат."
            else:
                return
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                text,
                reply_markup=_manage_links_markup(post_id) if post_id else None,
            )
        await callback.answer()

    @router.message(ChannelImportState.waiting_stock)
    async def receive_candidate_stock(message: Message, state: FSMContext):
        if not message.from_user:
            return
        shop_id = get_shop_id()
        if await _owner_shop(shop_id, message.from_user.id) is None:
            await message.answer("Доступно только владельцу магазина.")
            await state.clear()
            return
        raw_value = (message.text or "").strip()
        if raw_value.casefold() == "отмена":
            await state.clear()
            await message.answer("Ввод остатка отменён.")
            return
        try:
            stock = int(raw_value)
            if stock < 0:
                raise ValueError
        except ValueError:
            await message.answer("Введите целое число от 0 или отправьте «отмена».")
            return

        data = await state.get_data()
        candidate_id = int(data.get("candidate_id", 0))
        variant_index = int(data.get("variant_index", 0))
        candidate = await ChannelImportService.get_candidate(shop_id, candidate_id)
        if candidate is None:
            await state.clear()
            await message.answer("Черновик больше не найден.")
            return
        variants = [dict(item) for item in (candidate.get("variants") or [])]
        if variant_index >= len(variants):
            await state.clear()
            await message.answer("Вариант товара больше не найден.")
            return
        variants[variant_index]["stock"] = stock
        await ChannelImportService.update_candidate(
            shop_id, candidate_id, {"variants": variants}
        )

        next_index = _next_missing_stock(variants, variant_index + 1)
        if next_index is not None:
            await state.update_data(variant_index=next_index)
            await message.answer(
                _stock_prompt(variants[next_index], next_index, len(variants))
            )
            return

        await state.clear()
        try:
            product_id = await ChannelImportService.approve_candidate(
                shop_id, candidate_id
            )
        except ValueError as exc:
            await message.answer(
                f"Остаток сохранён, но товар пока нельзя опубликовать: {exc}"
            )
            return
        await message.answer(
            f"Товар опубликован, ID {product_id}.",
            reply_markup=_manage_links_markup(candidate["post"]["id"]),
        )

    @router.callback_query(F.data.startswith("cil:"))
    async def product_link_action(callback: CallbackQuery, state: FSMContext):
        if not callback.from_user or not callback.data:
            return
        shop_id = get_shop_id()
        if await _owner_shop(shop_id, callback.from_user.id) is None:
            await callback.answer("Доступно только владельцу", show_alert=True)
            return
        parts = callback.data.split(":")
        action = parts[1]
        try:
            if action == "show":
                post_id = int(parts[2])
                if callback.message:
                    await _send_links(callback.message, shop_id, post_id)
            elif action == "add":
                post_id = int(parts[2])
                await state.set_state(ChannelImportState.waiting_product_search)
                await state.set_data({"link_mode": "add", "post_id": post_id})
                if callback.message:
                    await callback.message.answer("Введите ID, SKU или часть названия товара.")
            elif action == "replace":
                post_id, link_id = int(parts[2]), int(parts[3])
                await state.set_state(ChannelImportState.waiting_product_search)
                await state.set_data(
                    {"link_mode": "replace", "post_id": post_id, "link_id": link_id}
                )
                if callback.message:
                    await callback.message.answer("Введите ID, SKU или часть названия нового товара.")
            elif action == "remove":
                post_id, link_id = int(parts[2]), int(parts[3])
                await ChannelPostButtonService.remove_link(shop_id, post_id, link_id)
                if callback.message:
                    await callback.message.answer("Товар отвязан от публикации.")
                    await _send_links(callback.message, shop_id, post_id)
            elif action in {"retry", "force"}:
                post_id = int(parts[2])
                try:
                    await ChannelPostButtonService.retry_post(
                        shop_id,
                        post_id,
                        allow_replace_unknown=action == "force",
                    )
                except ValueError as exc:
                    if "неизвестно" in str(exc).casefold() and callback.message:
                        await callback.message.answer(
                            str(exc),
                            reply_markup=InlineKeyboardMarkup(
                                inline_keyboard=[
                                    [
                                        InlineKeyboardButton(
                                            text="Заменить исходные кнопки",
                                            callback_data=f"cil:force:{post_id}",
                                        )
                                    ]
                                ]
                            ),
                        )
                        await callback.answer()
                        return
                    raise
                if callback.message:
                    await callback.message.answer("Синхронизация поставлена в очередь.")
            elif action == "choose":
                product_id = int(parts[2])
                data = await state.get_data()
                post_id = int(data.get("post_id", 0))
                if data.get("link_mode") == "replace":
                    await ChannelPostButtonService.replace_link(
                        shop_id, post_id, int(data["link_id"]), product_id
                    )
                else:
                    await ChannelPostButtonService.add_link(shop_id, post_id, product_id)
                await state.clear()
                if callback.message:
                    await callback.message.answer("Привязка сохранена.")
                    await _send_links(callback.message, shop_id, post_id)
            else:
                return
        except (ValueError, IndexError) as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        await callback.answer()

    @router.message(ChannelImportState.waiting_product_search)
    async def search_link_product(message: Message, state: FSMContext):
        if not message.from_user:
            return
        shop_id = get_shop_id()
        if await _owner_shop(shop_id, message.from_user.id) is None:
            await state.clear()
            return
        query = (message.text or "").strip()
        if query.casefold() == "отмена":
            await state.clear()
            await message.answer("Выбор товара отменён.")
            return
        products = await ChannelPostButtonService.search_products(shop_id, query)
        if not products:
            await message.answer("Активные товары не найдены. Попробуйте другой запрос или «отмена».")
            return
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"#{product['id']} {product['name'][:40]}",
                        callback_data=f"cil:choose:{product['id']}",
                    )
                ]
                for product in products
            ]
        )
        await message.answer("Выберите товар:", reply_markup=keyboard)

    return router
