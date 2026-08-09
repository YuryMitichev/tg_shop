"""Тесты карточки магазина с кнопками действий и удаления магазина."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from app.services.shop_service import ShopService


def _make_callback(data="delete_shop:2", user_id=111):
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = User(id=user_id, is_bot=False, first_name="Test")
    cb.message = MagicMock(spec=Message)
    cb.message.chat = Chat(id=1, type="private")
    cb.message.message_id = 1
    cb.message.answer = AsyncMock(return_value=MagicMock(message_id=2))
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.delete = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _shop_dict(shop_id=2, owner_id=111, name="Мой магазин", bot_username=None):
    return {
        "id": shop_id,
        "name": name,
        "owner_telegram_id": owner_id,
        "is_active": True,
        "bot_username": bot_username,
    }


class TestShopActionsKeyboard:
    """Клавиатура действий магазина содержит нужные кнопки."""

    def test_has_subscription_and_delete_callbacks(self):
        from app.bot.platform.bot import _shop_actions_kb

        kb = _shop_actions_kb(_shop_dict())
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "sub_shop:2" in callbacks
        assert "delete_shop:2" in callbacks

    def test_no_mini_app_link_in_keyboard(self):
        from app.bot.platform.bot import _shop_actions_kb

        kb = _shop_actions_kb(_shop_dict(bot_username="my_shop_bot"))
        urls = [btn.url for row in kb.inline_keyboard for btn in row if btn.url]
        assert urls == []

    def test_no_shop_link_when_username_missing(self):
        from app.bot.platform.bot import _shop_actions_kb

        with patch("app.bot.platform.bot.settings") as mock_settings:
            mock_settings.admin_panel_url = None
            mock_settings.webapp_enabled = True
            mock_settings.webapp_url = "https://shop.example.com/app/"
            kb = _shop_actions_kb(_shop_dict(bot_username=None))

        urls = [btn.url for row in kb.inline_keyboard for btn in row if btn.url]
        assert urls == []


class TestDeleteShopConfirmation:
    """Удаление магазина: подтверждение и проверка владельца."""

    async def test_owner_gets_confirmation(self):
        from app.bot.platform.bot import on_delete_shop

        cb = _make_callback(data="delete_shop:2", user_id=111)

        with patch.object(
            ShopService, "get", new_callable=AsyncMock, return_value=_shop_dict(owner_id=111)
        ):
            await on_delete_shop(cb)

        cb.message.answer.assert_called_once()
        markup = cb.message.answer.call_args.kwargs.get("reply_markup")
        callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert "delete_shop_confirm:2" in callbacks
        assert "delete_shop_cancel" in callbacks

    async def test_non_owner_denied(self):
        from app.bot.platform.bot import on_delete_shop

        cb = _make_callback(data="delete_shop:2", user_id=999)

        with patch.object(
            ShopService, "get", new_callable=AsyncMock, return_value=_shop_dict(owner_id=111)
        ):
            await on_delete_shop(cb)

        cb.answer.assert_called_once()
        assert cb.answer.call_args.kwargs.get("show_alert") is True
        cb.message.answer.assert_not_called()

    async def test_not_found_alert(self):
        from app.bot.platform.bot import on_delete_shop

        cb = _make_callback(data="delete_shop:99", user_id=111)

        with patch.object(ShopService, "get", new_callable=AsyncMock, return_value=None):
            await on_delete_shop(cb)

        cb.answer.assert_called_once()
        assert cb.answer.call_args.kwargs.get("show_alert") is True


class TestDeleteShopConfirm:
    """Подтверждение удаления: бот останавливается, магазин удаляется."""

    async def test_owner_delete_succeeds(self, db_session, seed_data):
        from app.bot.platform.bot import on_delete_shop_confirm
        from app.models.shop import Shop
        from app.utils.crypto import encrypt, token_hash

        session_maker = db_session
        async with session_maker() as session:
            session.add(Shop(
                id=2, name="Второй магазин",
                bot_token=encrypt("test:token2"),
                bot_token_hash=token_hash("test:token2"),
                owner_telegram_id=1,
            ))
            await session.commit()

        cb = _make_callback(data="delete_shop_confirm:2", user_id=1)

        with patch("app.bot.platform.bot.stop_shop_bot", new_callable=AsyncMock):
            await on_delete_shop_confirm(cb)

        cb.message.edit_text.assert_called_once()
        assert "удалён" in cb.message.edit_text.call_args.args[0].lower()

        assert await ShopService.get(2) is None

    async def test_non_owner_denied(self, db_session, seed_data):
        from app.bot.platform.bot import on_delete_shop_confirm
        from app.models.shop import Shop
        from app.utils.crypto import encrypt, token_hash

        session_maker = db_session
        async with session_maker() as session:
            session.add(Shop(
                id=2, name="Второй магазин",
                bot_token=encrypt("test:token2"),
                bot_token_hash=token_hash("test:token2"),
                owner_telegram_id=1,
            ))
            await session.commit()

        cb = _make_callback(data="delete_shop_confirm:2", user_id=999)

        with patch("app.bot.platform.bot.stop_shop_bot", new_callable=AsyncMock) as mock_stop:
            await on_delete_shop_confirm(cb)

        mock_stop.assert_not_called()
        cb.answer.assert_called_once()
        assert cb.answer.call_args.kwargs.get("show_alert") is True
        assert await ShopService.get(2) is not None


class TestDeleteShopCancel:
    """Отмена удаления убирает сообщение подтверждения."""

    async def test_cancel_deletes_message(self):
        from app.bot.platform.bot import on_delete_shop_cancel

        cb = _make_callback(data="delete_shop_cancel")
        await on_delete_shop_cancel(cb)

        cb.message.delete.assert_called_once()
        cb.answer.assert_called_once()
