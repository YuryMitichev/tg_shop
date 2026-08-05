"""Тесты подписочного гейтинга для админ-хендлеров бота."""
from datetime import datetime, timedelta, timezone

from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import CallbackQuery, Chat, Message, User

from app.bot.filters.subscription import SubscriptionActive
from app.models.subscription import Subscription, SubscriptionPlan


def _make_callback():
    cb = MagicMock(spec=CallbackQuery)
    cb.from_user = User(id=1, is_bot=False, first_name="Admin")
    cb.answer = AsyncMock()
    return cb


def _make_message():
    msg = MagicMock(spec=Message)
    msg.from_user = User(id=1, is_bot=False, first_name="Admin")
    msg.answer = AsyncMock()
    return msg


async def _seed_active_subscription(session_maker):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with session_maker() as session:
        session.add(SubscriptionPlan(
            id=1, name="Тест", price=690, duration_days=30, is_trial=False,
        ))
        await session.commit()
        session.add(Subscription(
            shop_id=1, plan_id=1, status="active",
            started_at=now, expires_at=now + timedelta(days=25),
        ))
        await session.commit()


class TestSubscriptionActiveFilter:

    async def test_blocks_callback_when_expired(self, db_session, seed_data):
        filt = SubscriptionActive()
        cb = _make_callback()

        result = await filt(cb)

        assert result is False
        cb.answer.assert_called_once()
        alert_text = cb.answer.call_args.kwargs.get("text", "")
        assert "истекла" in alert_text.lower()
        assert cb.answer.call_args.kwargs.get("show_alert") is True

    async def test_blocks_message_when_expired(self, db_session, seed_data):
        filt = SubscriptionActive()
        msg = _make_message()

        result = await filt(msg)

        assert result is False
        msg.answer.assert_called_once()
        assert "истекла" in msg.answer.call_args.kwargs["text"].lower()

    async def test_passes_when_active(self, db_session, seed_data):
        await _seed_active_subscription(db_session)

        filt = SubscriptionActive()
        cb = _make_callback()

        result = await filt(cb)

        assert result is True
        cb.answer.assert_not_called()


class TestAdminRouterFiltersApplied:

    def test_catalog_router_has_subscription_filter(self):
        from app.bot.handlers.admin.catalog import setup_catalog_router

        router = setup_catalog_router()
        callbacks = [fo.callback for fo in (router.callback_query._handler.filters or [])]
        assert any(isinstance(c, SubscriptionActive) for c in callbacks), (
            "catalog router must have SubscriptionActive root filter"
        )

    def test_messages_router_has_subscription_filter(self):
        from app.bot.handlers.admin.messages import setup_messages_router

        router = setup_messages_router()
        callbacks = [fo.callback for fo in (router.callback_query._handler.filters or [])]
        assert any(isinstance(c, SubscriptionActive) for c in callbacks)

    def test_promos_router_has_subscription_filter(self):
        from app.bot.handlers.admin.promos import setup_promos_router

        router = setup_promos_router()
        callbacks = [fo.callback for fo in (router.callback_query._handler.filters or [])]
        assert any(isinstance(c, SubscriptionActive) for c in callbacks)

    def test_orders_router_does_not_have_subscription_filter(self):
        from app.bot.handlers.admin.orders import setup_orders_router

        router = setup_orders_router()
        callbacks = [fo.callback for fo in (router.callback_query._handler.filters or [])]
        assert not any(isinstance(c, SubscriptionActive) for c in callbacks), (
            "orders router must NOT have SubscriptionActive filter"
        )
