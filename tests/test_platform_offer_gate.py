"""Тесты проверки принятия оферты перед оплатой подписки."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from app.services.offer_agreement_service import OfferAgreementService
from app.services.platform_settings_service import PlatformSettingsService


def _make_callback(data="pay:1:2", user_id=111):
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = User(id=user_id, is_bot=False, first_name="Test")
    cb.message = MagicMock(spec=Message)
    cb.message.chat = Chat(id=1, type="private")
    cb.message.message_id = 1
    cb.message.answer = AsyncMock(return_value=MagicMock(message_id=2))
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()
    return cb


@pytest.fixture
def mock_yookassa():
    with patch(
        "app.bot.platform.bot.settings"
    ) as mock_settings, patch.object(
        PlatformSettingsService,
        "is_yookassa_enabled",
        new_callable=AsyncMock,
        return_value=True,
    ):
        mock_settings.yookassa_enabled = True
        yield mock_settings


class TestPayRequiresOfferAcceptance:
    """Оплата без принятия оферты блокируется."""

    async def test_pay_blocked_without_acceptance(self, db_session, seed_data, mock_yookassa):
        from app.bot.platform.bot import on_pay

        cb = _make_callback(data="pay:1:2")

        with patch.object(
            OfferAgreementService, "has_accepted", new_callable=AsyncMock, return_value=False
        ):
            await on_pay(cb)

        cb.answer.assert_called_once()
        alert_text = cb.answer.call_args.kwargs.get("show_alert")
        assert alert_text is True

        cb.message.answer.assert_called_once()
        sent_text = cb.message.answer.call_args.args[0]
        assert "оферты" in sent_text.lower()

    async def test_pay_shows_accept_button_with_callback(self, db_session, seed_data, mock_yookassa):
        from app.bot.platform.bot import on_pay

        cb = _make_callback(data="pay:1:2")

        with patch.object(
            OfferAgreementService, "has_accepted", new_callable=AsyncMock, return_value=False
        ):
            await on_pay(cb)

        reply_markup = cb.message.answer.call_args.kwargs.get("reply_markup")
        assert reply_markup is not None

        button_texts = [
            btn.text for row in reply_markup.inline_keyboard for btn in row
        ]
        assert any("Принять" in t for t in button_texts)

        button_callbacks = [
            btn.callback_data for row in reply_markup.inline_keyboard for btn in row
        ]
        assert any("accept_offer_pay:1:2" in c for c in button_callbacks)

    async def test_pay_allowed_with_acceptance(self, db_session, seed_data, mock_yookassa):
        from app.bot.platform.bot import on_pay

        cb = _make_callback(data="pay:1:2")

        mock_payment = {"payment_id": "yk_123", "confirmation_url": "https://yoomoney.ru/checkout?id=123"}

        with patch.object(
            OfferAgreementService, "has_accepted", new_callable=AsyncMock, return_value=True
        ), patch(
            "app.bot.platform.bot.SubscriptionPaymentService.create_payment",
            new_callable=AsyncMock,
            return_value=mock_payment,
        ):
            await on_pay(cb)

        alert_args = cb.answer.call_args_list
        assert any("Создаю платёж" in str(a) for a in alert_args)

        assert cb.message.answer.call_count >= 1
        last_call_text = cb.message.answer.call_args.kwargs.get("text") or ""
        if not last_call_text:
            last_call_text = cb.message.answer.call_args.args[-1] if cb.message.answer.call_args.args else ""
        assert "оплат" in last_call_text.lower() or "Нажмите" in last_call_text


class TestAcceptOfferAndPay:
    """Принятие оферты через кнопку оплаты → оферта принята + платёж создан."""

    async def test_accept_offer_and_pay_creates_acceptance(self, db_session, seed_data, mock_yookassa):
        from app.bot.platform.bot import on_accept_offer_and_pay

        cb = _make_callback(data="accept_offer_pay:1:2", user_id=222)

        mock_payment = {"payment_id": "yk_456", "confirmation_url": "https://yoomoney.ru/checkout?id=456"}

        with patch(
            "app.bot.platform.bot.SubscriptionPaymentService.create_payment",
            new_callable=AsyncMock,
            return_value=mock_payment,
        ):
            await on_accept_offer_and_pay(cb)

        accepted = await OfferAgreementService.has_accepted(222)
        assert accepted is True

    async def test_accept_offer_and_pay_creates_payment(self, db_session, seed_data, mock_yookassa):
        from app.bot.platform.bot import on_accept_offer_and_pay

        cb = _make_callback(data="accept_offer_pay:1:2", user_id=333)

        mock_payment = {"payment_id": "yk_789", "confirmation_url": "https://yoomoney.ru/checkout?id=789"}

        with patch(
            "app.bot.platform.bot.SubscriptionPaymentService.create_payment",
            new_callable=AsyncMock,
            return_value=mock_payment,
        ) as mock_create:
            await on_accept_offer_and_pay(cb)

        mock_create.assert_called_once_with(shop_id=1, plan_id=2)

        texts = [str(c) for c in cb.message.answer.call_args_list]
        assert any("приняли" in t.lower() for t in texts)

    async def test_accept_offer_and_pay_idempotent(self, db_session, seed_data, mock_yookassa):
        """Повторное принятие оферты не вызывает ошибку."""
        from app.bot.platform.bot import on_accept_offer_and_pay

        await OfferAgreementService.accept(telegram_user_id=444, full_name="Already")

        cb = _make_callback(data="accept_offer_pay:1:2", user_id=444)

        mock_payment = {"payment_id": "yk_000", "confirmation_url": "https://yoomoney.ru/checkout?id=000"}

        with patch(
            "app.bot.platform.bot.SubscriptionPaymentService.create_payment",
            new_callable=AsyncMock,
            return_value=mock_payment,
        ):
            await on_accept_offer_and_pay(cb)

        accepted = await OfferAgreementService.has_accepted(444)
        assert accepted is True


class TestAcceptOfferStandalone:
    """Обычное принятие оферты (без оплаты) продолжает работать."""

    async def test_accept_offer_creates_acceptance(self, db_session, seed_data):
        from app.bot.platform.bot import on_accept_offer

        cb = _make_callback(data="accept_offer", user_id=555)

        await on_accept_offer(cb)

        accepted = await OfferAgreementService.has_accepted(555)
        assert accepted is True

        cb.message.edit_reply_markup.assert_called_once()
