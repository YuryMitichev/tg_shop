import asyncio
from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.models.cart_item import CartItem
from app.models.channel_import import (
    ChannelAttributionEvent,
    ChannelConnection,
    ChannelPost,
    ProductSourceRef,
)
from app.models.order import Order
from app.models.order_item import OrderItem
from app.services.cart_service import CartService
from app.services.channel_attribution_service import ChannelAttributionService
from app.services.channel_post_button_service import product_start_param
from app.services.channel_metrics_service import ChannelMetricsService
from app.services.channel_metrics_service import _fetch_public_views
from app.services.channel_metrics_service import parse_public_views_html
from app.services.order_admin_service import OrderAdminService
from app.services.order_service import OrderService


async def _source(db_session):
    async with db_session() as session:
        connection = ChannelConnection(
            shop_id=1,
            channel_id=-100123,
            channel_title="Тестовый канал",
            channel_username="test_channel",
            connected_by=1,
        )
        session.add(connection)
        await session.flush()
        post = ChannelPost(
            shop_id=1,
            connection_id=connection.id,
            telegram_message_id=77,
            text="Пост с товаром",
            published_at=datetime.now(),
            telegram_views=100,
        )
        session.add(post)
        await session.flush()
        ref = ProductSourceRef(
            shop_id=1,
            product_id=1,
            connection_id=connection.id,
            telegram_message_id=77,
            candidate_position=0,
            public_token="sourceabc",
        )
        session.add(ref)
        await session.commit()
        return post.id, ref.id


def _enable(monkeypatch):
    monkeypatch.setattr(settings, "channel_attribution_enabled", True)
    monkeypatch.setattr(settings, "channel_attribution_pilot_shop_id", 1)


async def test_events_are_idempotent_and_reported(
    db_session, seed_data, monkeypatch
):
    _enable(monkeypatch)
    post_id, _ = await _source(db_session)

    assert await ChannelAttributionService.record_event(
        1, 111, 1, "sourceabc", "product_open", "open-1"
    )
    assert not await ChannelAttributionService.record_event(
        1, 111, 1, "sourceabc", "product_open", "open-1"
    )

    async with db_session() as session:
        rows = (await session.execute(select(ChannelAttributionEvent))).scalars().all()
        assert len(rows) == 1
        assert rows[0].post_id == post_id

    report = await ChannelAttributionService.publication_report(1)
    assert report["summary"]["views"] == 100
    assert report["summary"]["opens"] == 1
    assert report["summary"]["ctr"] == 1.0


async def test_source_moves_from_cart_to_confirmed_sale(
    db_session, seed_data, monkeypatch
):
    _enable(monkeypatch)
    post_id, ref_id = await _source(db_session)

    error = await CartService.add_item(
        1,
        111,
        product_id=1,
        variant_id=1,
        quantity=1,
        source_ref_token="sourceabc",
    )
    assert error is None

    async with db_session() as session:
        cart = (await session.execute(select(CartItem))).scalar_one()
        assert cart.source_ref_id == ref_id
        assert cart.source_post_id == post_id

    created = await OrderService.create_order(
        1, 111, "Иван", "+7", "Адрес", payment_method="manual"
    )
    report_before = await ChannelAttributionService.publication_report(1)
    assert report_before["summary"]["paid_orders"] == 0
    assert report_before["summary"]["revenue"] == 0

    await OrderAdminService.set_order_status(1, created["order_id"], "paid")
    await OrderAdminService.set_order_status(1, created["order_id"], "paid")

    async with db_session() as session:
        order = await session.get(Order, created["order_id"])
        order_item = (await session.execute(select(OrderItem))).scalar_one()
        assert order.payment_confirmed_at is not None
        assert order.payment_confirmation_source == "manual"
        assert order_item.source_post_id == post_id

    report = await ChannelAttributionService.publication_report(1)
    assert report["summary"]["paid_orders"] == 1
    assert report["summary"]["revenue"] == 450


async def test_invalid_source_is_ignored(db_session, seed_data, monkeypatch):
    _enable(monkeypatch)
    await _source(db_session)
    assert not await ChannelAttributionService.record_event(
        1, 111, 1, "wrong", "product_open", "bad-1"
    )


def test_start_param_with_source_is_short_and_backward_compatible():
    assert product_start_param(17, 125) == "shop_17_product_125"
    value = product_start_param(17, 125, "sourceabc")
    assert value == "shop_17_product_125_ref_sourceabc"
    assert len(value) <= 64


async def test_view_refresh_fails_safely_without_mtproto(
    db_session, seed_data, monkeypatch
):
    import pytest

    _enable(monkeypatch)
    await _source(db_session)
    monkeypatch.setattr(settings, "telegram_api_id", None)
    monkeypatch.setattr(settings, "telegram_api_hash", None)
    monkeypatch.setattr(settings, "telegram_session", None)

    with pytest.raises(RuntimeError, match="MTProto"):
        await ChannelMetricsService.refresh_shop(1)


def test_public_views_parser_supports_telegram_abbreviations():
    template = '<span class="tgme_widget_message_views">{}</span>'
    assert parse_public_views_html(template.format("1")) == 1
    assert parse_public_views_html(template.format("3.42K")) == 3420
    assert parse_public_views_html(template.format("1,2M")) == 1_200_000


def test_public_views_parser_rejects_missing_or_unbounded_values():
    import pytest

    with pytest.raises(ValueError):
        parse_public_views_html("<html></html>")
    with pytest.raises(ValueError):
        parse_public_views_html(
            '<span class="tgme_widget_message_views">99B</span>'
        )


async def test_public_metrics_rejects_untrusted_username_before_request():
    import pytest

    with pytest.raises(ValueError, match="публичная ссылка"):
        await _fetch_public_views(None, "evil.example", 77)


async def test_public_metrics_fallback_updates_views_without_mtproto(
    db_session, seed_data, monkeypatch
):
    import app.services.channel_metrics_service as metrics_module

    _enable(monkeypatch)
    post_id, _ = await _source(db_session)
    monkeypatch.setattr(settings, "telegram_api_id", None)
    monkeypatch.setattr(settings, "telegram_api_hash", None)
    monkeypatch.setattr(settings, "telegram_session", None)
    monkeypatch.setattr(settings, "channel_public_metrics_enabled", True)

    async def fake_fetch(http, username, message_id):
        assert username == "test_channel"
        assert message_id == 77
        return 125

    monkeypatch.setattr(metrics_module, "_fetch_public_views", fake_fetch)

    assert await ChannelMetricsService.refresh_shop(1) == 1
    async with db_session() as session:
        post = await session.get(ChannelPost, post_id)
        assert post.telegram_views == 125
        assert post.metrics_updated_at is not None


async def test_public_metrics_failure_preserves_last_known_views(
    db_session, seed_data, monkeypatch
):
    import pytest
    import app.services.channel_metrics_service as metrics_module

    _enable(monkeypatch)
    post_id, _ = await _source(db_session)
    monkeypatch.setattr(settings, "telegram_api_id", None)
    monkeypatch.setattr(settings, "telegram_api_hash", None)
    monkeypatch.setattr(settings, "telegram_session", None)
    monkeypatch.setattr(settings, "channel_public_metrics_enabled", True)

    async def failed_fetch(http, username, message_id):
        raise TimeoutError("Telegram unavailable")

    monkeypatch.setattr(metrics_module, "_fetch_public_views", failed_fetch)

    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        await ChannelMetricsService.refresh_shop(1)
    async with db_session() as session:
        assert (await session.get(ChannelPost, post_id)).telegram_views == 100


async def test_public_metrics_deadline_is_bounded_and_preserves_views(
    db_session, seed_data, monkeypatch
):
    import pytest
    import app.services.channel_metrics_service as metrics_module

    _enable(monkeypatch)
    post_id, _ = await _source(db_session)
    monkeypatch.setattr(settings, "telegram_api_id", None)
    monkeypatch.setattr(settings, "telegram_api_hash", None)
    monkeypatch.setattr(settings, "telegram_session", None)
    monkeypatch.setattr(settings, "channel_public_metrics_enabled", True)
    monkeypatch.setattr(metrics_module, "_PUBLIC_REFRESH_DEADLINE_SECONDS", 0.01)

    async def slow_fetch(http, username, message_id):
        await asyncio.sleep(1)
        return 999

    monkeypatch.setattr(metrics_module, "_fetch_public_views", slow_fetch)

    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        await ChannelMetricsService.refresh_shop(1)
    async with db_session() as session:
        assert (await session.get(ChannelPost, post_id)).telegram_views == 100
