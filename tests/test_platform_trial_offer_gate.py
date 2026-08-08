"""Тесты проверки принятия оферты + политики перед активацией триала."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from app.services.offer_agreement_service import OfferAgreementService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(user_id=111, text="123:ABCtoken"):
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = User(id=user_id, is_bot=False, first_name="Test")
    msg.chat = Chat(id=1, type="private")
    msg.message_id = 1
    msg.answer = AsyncMock(return_value=MagicMock(message_id=2))
    msg.answer_document = AsyncMock(return_value=MagicMock(message_id=2))
    return msg


def _make_callback(data="accept_offer_trial:1", user_id=111):
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = User(id=user_id, is_bot=False, first_name="Test")
    cb.message = MagicMock(spec=Message)
    cb.message.chat = Chat(id=1, type="private")
    cb.message.message_id = 1
    cb.message.answer = AsyncMock(return_value=MagicMock(message_id=2))
    cb.message.answer_document = AsyncMock(return_value=MagicMock(message_id=2))
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _make_state(data=None):
    """Создаёт mock FSMContext с предустановленными данными."""
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.update_data = AsyncMock()
    return state


def _shop_dict(shop_id=99, name="Тест", owner_id=111, bot_token="123:ABCtoken"):
    return {
        "id": shop_id,
        "name": name,
        "owner_telegram_id": owner_id,
        "bot_token": bot_token,
        "is_active": True,
    }


_BOT_INFO = {"id": 999, "username": "testbot", "first_name": "Test Bot"}


# ---------------------------------------------------------------------------
# on_token_received: gate before trial
# ---------------------------------------------------------------------------

class TestTokenReceivedShowsGate:
    """Если пользователь ещё не принял оферту — показываем гейт, триал не активируем."""

    async def test_shows_gate_message_without_acceptance(self):
        from app.bot.platform.bot import on_token_received

        msg = _make_message()
        state = _make_state(data={"shop_name": "Мой магазин"})

        with patch(
            "app.bot.platform.bot.ShopService.get_by_bot_token",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.bot.platform.bot._validate_bot_token",
            new_callable=AsyncMock,
            return_value=_BOT_INFO,
        ), patch(
            "app.bot.platform.bot.ShopService.create",
            new_callable=AsyncMock,
            return_value=_shop_dict(),
        ), patch(
            "app.bot.platform.bot.AdminUserService.add",
            new_callable=AsyncMock,
        ), patch.object(
            OfferAgreementService, "has_accepted", new_callable=AsyncMock, return_value=False
        ), patch(
            "app.bot.platform.bot.SubscriptionService.start_trial",
            new_callable=AsyncMock,
        ) as mock_trial:
            await on_token_received(msg, state)

        # Триал НЕ активирован
        mock_trial.assert_not_called()

        # Найдено сообщение с упоминанием оферты и политики
        sent_texts = [str(c.args[0]) if c.args else str(c) for c in msg.answer.call_args_list]
        joined = " ".join(sent_texts)
        assert "оферты" in joined.lower()
        assert "политики" in joined.lower() or "конфиденциальности" in joined.lower()

    async def test_gate_has_accept_and_read_buttons(self):
        from app.bot.platform.bot import on_token_received

        msg = _make_message()
        state = _make_state(data={"shop_name": "Мой магазин"})

        with patch(
            "app.bot.platform.bot.ShopService.get_by_bot_token",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.bot.platform.bot._validate_bot_token",
            new_callable=AsyncMock,
            return_value=_BOT_INFO,
        ), patch(
            "app.bot.platform.bot.ShopService.create",
            new_callable=AsyncMock,
            return_value=_shop_dict(shop_id=42),
        ), patch(
            "app.bot.platform.bot.AdminUserService.add",
            new_callable=AsyncMock,
        ), patch.object(
            OfferAgreementService, "has_accepted", new_callable=AsyncMock, return_value=False
        ):
            await on_token_received(msg, state)

        # Ищем вызов с reply_markup
        markup_call = None
        for c in msg.answer.call_args_list:
            if c.kwargs.get("reply_markup"):
                markup_call = c
                break

        assert markup_call is not None, "Нет вызова с inline-клавиатурой"

        buttons = [
            btn
            for row in markup_call.kwargs["reply_markup"].inline_keyboard
            for btn in row
        ]
        texts = [b.text for b in buttons]
        callbacks = [b.callback_data for b in buttons]

        assert any("Принять" in t for t in texts)
        assert "accept_offer_trial:42" in callbacks
        assert "show_offer" in callbacks
        assert "show_privacy" in callbacks

    async def test_state_data_stored_before_gate(self):
        """shop_id и bot_username сохраняются в state до показа гейта."""
        from app.bot.platform.bot import on_token_received

        msg = _make_message()
        state = _make_state(data={"shop_name": "Мой магазин"})

        with patch(
            "app.bot.platform.bot.ShopService.get_by_bot_token",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.bot.platform.bot._validate_bot_token",
            new_callable=AsyncMock,
            return_value=_BOT_INFO,
        ), patch(
            "app.bot.platform.bot.ShopService.create",
            new_callable=AsyncMock,
            return_value=_shop_dict(shop_id=55),
        ), patch(
            "app.bot.platform.bot.AdminUserService.add",
            new_callable=AsyncMock,
        ), patch.object(
            OfferAgreementService, "has_accepted", new_callable=AsyncMock, return_value=False
        ):
            await on_token_received(msg, state)

        state.update_data.assert_called_with(shop_id=55, bot_username="testbot")
        state.set_state.assert_called_with(None)


class TestTokenReceivedSkipsGateIfAccepted:
    """Если пользователь уже принял оферту — триал активируется сразу."""

    async def test_trial_activated_when_already_accepted(self):
        from app.bot.platform.bot import on_token_received

        msg = _make_message()
        state = _make_state(data={"shop_name": "Мой магазин"})

        with patch(
            "app.bot.platform.bot.ShopService.get_by_bot_token",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.bot.platform.bot._validate_bot_token",
            new_callable=AsyncMock,
            return_value=_BOT_INFO,
        ), patch(
            "app.bot.platform.bot.ShopService.create",
            new_callable=AsyncMock,
            return_value=_shop_dict(shop_id=77),
        ), patch(
            "app.bot.platform.bot.AdminUserService.add",
            new_callable=AsyncMock,
        ), patch.object(
            OfferAgreementService, "has_accepted", new_callable=AsyncMock, return_value=True
        ), patch(
            "app.bot.platform.bot.SubscriptionService.start_trial",
            new_callable=AsyncMock,
        ) as mock_trial, patch(
            "app.bot.platform.bot.start_shop_bot",
            new_callable=AsyncMock,
        ) as mock_start:
            await on_token_received(msg, state)

        mock_trial.assert_called_once_with(77)
        mock_start.assert_called_once_with(77)
        state.clear.assert_called_once()


# ---------------------------------------------------------------------------
# on_accept_offer_and_trial
# ---------------------------------------------------------------------------

class TestAcceptOfferAndTrial:
    """Принятие оферты+политики → активация триала и запуск бота."""

    async def test_accepts_offer(self, db_session, seed_data):
        from app.bot.platform.bot import on_accept_offer_and_trial

        cb = _make_callback(data="accept_offer_trial:1", user_id=600)
        state = _make_state(data={"shop_id": 1, "bot_username": "mybot"})

        with patch(
            "app.bot.platform.bot.ShopService.get",
            new_callable=AsyncMock,
            return_value=_shop_dict(shop_id=1),
        ), patch(
            "app.bot.platform.bot.SubscriptionService.start_trial",
            new_callable=AsyncMock,
        ), patch(
            "app.bot.platform.bot.start_shop_bot",
            new_callable=AsyncMock,
        ):
            await on_accept_offer_and_trial(cb, state)

        accepted = await OfferAgreementService.has_accepted(600)
        assert accepted is True

    async def test_activates_trial_and_starts_bot(self):
        from app.bot.platform.bot import on_accept_offer_and_trial

        cb = _make_callback(data="accept_offer_trial:1", user_id=601)
        state = _make_state(data={"shop_id": 1, "bot_username": "mybot"})

        with patch.object(
            OfferAgreementService, "accept", new_callable=AsyncMock
        ), patch(
            "app.bot.platform.bot.ShopService.get",
            new_callable=AsyncMock,
            return_value=_shop_dict(shop_id=1),
        ), patch(
            "app.bot.platform.bot.SubscriptionService.start_trial",
            new_callable=AsyncMock,
        ) as mock_trial, patch(
            "app.bot.platform.bot.start_shop_bot",
            new_callable=AsyncMock,
        ) as mock_start:
            await on_accept_offer_and_trial(cb, state)

        mock_trial.assert_called_once_with(1)
        mock_start.assert_called_once_with(1)
        state.clear.assert_called_once()

    async def test_success_message_contains_bot_username(self):
        from app.bot.platform.bot import on_accept_offer_and_trial

        cb = _make_callback(data="accept_offer_trial:1", user_id=602)
        state = _make_state(data={"shop_id": 1, "bot_username": "coolshop"})

        with patch.object(
            OfferAgreementService, "accept", new_callable=AsyncMock
        ), patch(
            "app.bot.platform.bot.ShopService.get",
            new_callable=AsyncMock,
            return_value=_shop_dict(shop_id=1, name="Cool Shop"),
        ), patch(
            "app.bot.platform.bot.SubscriptionService.start_trial",
            new_callable=AsyncMock,
        ), patch(
            "app.bot.platform.bot.start_shop_bot",
            new_callable=AsyncMock,
        ):
            await on_accept_offer_and_trial(cb, state)

        all_texts = " ".join(
            str(c.args[0]) if c.args else str(c)
            for c in cb.message.answer.call_args_list
        )
        assert "@coolshop" in all_texts
        assert "7 дней" in all_texts

    async def test_idempotent_offer_acceptance(self, db_session, seed_data):
        """Повторное принятие оферты не вызывает ошибку."""
        from app.bot.platform.bot import on_accept_offer_and_trial

        await OfferAgreementService.accept(telegram_user_id=603, full_name="Already")

        cb = _make_callback(data="accept_offer_trial:1", user_id=603)
        state = _make_state(data={"shop_id": 1, "bot_username": "mybot"})

        with patch(
            "app.bot.platform.bot.ShopService.get",
            new_callable=AsyncMock,
            return_value=_shop_dict(shop_id=1),
        ), patch(
            "app.bot.platform.bot.SubscriptionService.start_trial",
            new_callable=AsyncMock,
        ), patch(
            "app.bot.platform.bot.start_shop_bot",
            new_callable=AsyncMock,
        ):
            await on_accept_offer_and_trial(cb, state)

        accepted = await OfferAgreementService.has_accepted(603)
        assert accepted is True

    async def test_shop_not_found_clears_state(self):
        from app.bot.platform.bot import on_accept_offer_and_trial

        cb = _make_callback(data="accept_offer_trial:999", user_id=604)
        state = _make_state(data={"shop_id": 999, "bot_username": "ghost"})

        with patch.object(
            OfferAgreementService, "accept", new_callable=AsyncMock
        ), patch(
            "app.bot.platform.bot.ShopService.get",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.bot.platform.bot.SubscriptionService.start_trial",
            new_callable=AsyncMock,
        ) as mock_trial, patch(
            "app.bot.platform.bot.start_shop_bot",
            new_callable=AsyncMock,
        ) as mock_start:
            await on_accept_offer_and_trial(cb, state)

        mock_trial.assert_not_called()
        mock_start.assert_not_called()
        state.clear.assert_called_once()

    async def test_fallback_revalidates_token_if_no_username(self):
        """Если bot_username отсутствует в state — повторная валидация токена."""
        from app.bot.platform.bot import on_accept_offer_and_trial

        cb = _make_callback(data="accept_offer_trial:1", user_id=605)
        state = _make_state(data={})

        with patch.object(
            OfferAgreementService, "accept", new_callable=AsyncMock
        ), patch(
            "app.bot.platform.bot.ShopService.get",
            new_callable=AsyncMock,
            return_value=_shop_dict(shop_id=1, bot_token="999:XYZ"),
        ), patch(
            "app.bot.platform.bot._validate_bot_token",
            new_callable=AsyncMock,
            return_value=_BOT_INFO,
        ) as mock_validate, patch(
            "app.bot.platform.bot.SubscriptionService.start_trial",
            new_callable=AsyncMock,
        ), patch(
            "app.bot.platform.bot.start_shop_bot",
            new_callable=AsyncMock,
        ):
            await on_accept_offer_and_trial(cb, state)

        mock_validate.assert_called_once_with("999:XYZ")


# ---------------------------------------------------------------------------
# on_show_privacy
# ---------------------------------------------------------------------------

class TestShowPrivacy:
    """Присылание политики конфиденциальности как файла."""

    async def test_sends_privacy_document(self):
        from app.bot.platform.bot import on_show_privacy

        cb = _make_callback(data="show_privacy", user_id=700)

        await on_show_privacy(cb)

        cb.message.answer_document.assert_called_once()
        caption = cb.message.answer_document.call_args.kwargs.get("caption", "")
        assert "КОНФИДЕНЦИАЛЬНОСТИ" in caption.upper()
        cb.answer.assert_called_once()

    async def test_returns_text_from_file(self):
        from app.services.offer_agreement_service import get_privacy_policy_text

        text = get_privacy_policy_text()
        assert len(text) > 100
        assert "персональных данных" in text.lower()


# ---------------------------------------------------------------------------
# on_show_offer
# ---------------------------------------------------------------------------

class TestShowOffer:
    """Присылание оферты как файла."""

    async def test_sends_offer_document(self):
        from app.bot.platform.bot import on_show_offer

        cb = _make_callback(data="show_offer", user_id=710)

        with patch.object(
            OfferAgreementService, "has_accepted", new_callable=AsyncMock, return_value=False
        ):
            await on_show_offer(cb)

        cb.message.answer_document.assert_called_once()
        caption = cb.message.answer_document.call_args.kwargs.get("caption", "")
        assert "ОФЕРТА" in caption.upper()
        cb.answer.assert_called_once()

    async def test_show_offer_followed_by_accept_button_when_not_accepted(self):
        from app.bot.platform.bot import on_show_offer

        cb = _make_callback(data="show_offer", user_id=711)

        with patch.object(
            OfferAgreementService, "has_accepted", new_callable=AsyncMock, return_value=False
        ):
            await on_show_offer(cb)

        # Document sent + follow-up message with accept button
        assert cb.message.answer.call_count >= 1
        reply_markup = cb.message.answer.call_args.kwargs.get("reply_markup")
        assert reply_markup is not None
        callbacks = [
            btn.callback_data
            for row in reply_markup.inline_keyboard
            for btn in row
        ]
        assert "accept_offer" in callbacks

    async def test_show_offer_shows_already_accepted_when_accepted(self):
        from app.bot.platform.bot import on_show_offer

        cb = _make_callback(data="show_offer", user_id=712)

        with patch.object(
            OfferAgreementService, "has_accepted", new_callable=AsyncMock, return_value=True
        ):
            await on_show_offer(cb)

        cb.message.answer_document.assert_called_once()
        follow_up = " ".join(
            str(c.args[0]) if c.args else str(c)
            for c in cb.message.answer.call_args_list
        )
        assert "приняли" in follow_up.lower()


# ---------------------------------------------------------------------------
# on_offer (command handler)
# ---------------------------------------------------------------------------

class TestOfferCommand:
    """Команда /offer — присылает файл оферты."""

    async def test_sends_offer_document(self):
        from app.bot.platform.bot import on_offer

        msg = _make_message()

        with patch.object(
            OfferAgreementService, "has_accepted", new_callable=AsyncMock, return_value=False
        ):
            await on_offer(msg)

        msg.answer_document.assert_called_once()
        caption = msg.answer_document.call_args.kwargs.get("caption", "")
        assert "ОФЕРТА" in caption.upper()

    async def test_followed_by_accept_button_when_not_accepted(self):
        from app.bot.platform.bot import on_offer

        msg = _make_message()

        with patch.object(
            OfferAgreementService, "has_accepted", new_callable=AsyncMock, return_value=False
        ):
            await on_offer(msg)

        reply_markup = msg.answer.call_args.kwargs.get("reply_markup")
        assert reply_markup is not None
        callbacks = [
            btn.callback_data
            for row in reply_markup.inline_keyboard
            for btn in row
        ]
        assert "accept_offer" in callbacks
