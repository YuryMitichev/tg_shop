from unittest.mock import AsyncMock

import pytest

from app.models.user_profile import UserProfile
from app.services.broadcast_service import BroadcastService, AUTO_TAGS, VIP_THRESHOLD, REGULAR_ORDERS
from app.services.crm_service import CrmService
from app.services.order_service import OrderService
from app.services.cart_service import CartService
from app.services.sales_service import SalesService
from app.models.order import Order


async def _create_order(db_session, tg_id=111, total=450):
    await CartService.add_item(1, tg_id, product_id=1, variant_id=1, quantity=1)
    result = await OrderService.create_order(
        shop_id=1,
        telegram_user_id=tg_id,
        full_name="Иван",
        phone="+7999",
        address="ул. Тест, 1",
    )
    async with db_session() as session:
        order = await session.get(Order, result["order_id"])
        SalesService.confirm_order(order, source="manual")
        await session.commit()


class TestParseTags:

    def test_empty(self):
        assert BroadcastService._parse_tags(None) == []

    def test_single(self):
        assert BroadcastService._parse_tags("VIP") == ["VIP"]

    def test_multiple(self):
        assert BroadcastService._parse_tags("VIP, Новичок, Постоянный") == ["VIP", "Новичок", "Постоянный"]


class TestPreviewRecipients:

    async def test_no_profiles(self, db_session, seed_data):
        result = await BroadcastService.preview_recipients(1)
        assert result["recipients_count"] == 0

    async def test_counts_all(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)
        await CrmService.get_or_create_profile(1, 222)

        result = await BroadcastService.preview_recipients(1)
        assert result["recipients_count"] == 2

    async def test_filter_by_tag(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)
        await CrmService.add_tag(1, 111, "VIP")
        await CrmService.get_or_create_profile(1, 222)

        result = await BroadcastService.preview_recipients(1, tags=["VIP"])
        assert result["recipients_count"] == 1
        assert 111 in result["telegram_ids"]


class TestAutoTagAllUsers:

    async def test_newbie_tag_for_no_orders(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)

        updated = await BroadcastService.auto_tag_all_users(1)
        assert updated == 1

        detail = await CrmService.get_user_detail(1, 111)
        assert AUTO_TAGS["newbie"] in detail["tags"]

    async def test_buyer_tag_for_orders(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)
        await _create_order(db_session, tg_id=111)

        await BroadcastService.auto_tag_all_users(1)

        detail = await CrmService.get_user_detail(1, 111)
        assert AUTO_TAGS["buyer"] in detail["tags"]
        assert AUTO_TAGS["newbie"] not in detail["tags"]

    async def test_regular_tag(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)
        for i in range(REGULAR_ORDERS):
            await _create_order(db_session, tg_id=111)

        await BroadcastService.auto_tag_all_users(1)

        detail = await CrmService.get_user_detail(1, 111)
        assert AUTO_TAGS["regular"] in detail["tags"]

    async def test_preserves_manual_tags(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)
        await CrmService.add_tag(1, 111, "Любимый")

        await BroadcastService.auto_tag_all_users(1)

        detail = await CrmService.get_user_detail(1, 111)
        assert "Любимый" in detail["tags"]
        assert AUTO_TAGS["newbie"] in detail["tags"]

    async def test_no_profiles(self, db_session, seed_data):
        updated = await BroadcastService.auto_tag_all_users(1)
        assert updated == 0


class TestCreateBroadcast:

    async def test_creates_broadcast(self, db_session, seed_data):
        broadcast = await BroadcastService.create_broadcast(
            shop_id=1,
            product_id=1,
            discount_percent=10,
        )
        assert broadcast.id is not None
        assert broadcast.product_name == "Кашемир"
        assert broadcast.discount_percent == 10
        assert broadcast.status == "draft"

    async def test_calculates_discounted_price(self, db_session, seed_data):
        broadcast = await BroadcastService.create_broadcast(
            shop_id=1,
            product_id=1,
            discount_percent=20,
            variant_id=1,
        )
        assert broadcast.original_price == 450
        assert broadcast.discounted_price == 360

    async def test_uses_cheapest_variant(self, db_session, seed_data):
        broadcast = await BroadcastService.create_broadcast(
            shop_id=1,
            product_id=1,
            discount_percent=10,
        )
        assert broadcast.original_price == 450

    async def test_product_not_found(self, db_session, seed_data):
        with pytest.raises(ValueError, match="Товар не найден"):
            await BroadcastService.create_broadcast(
                shop_id=1,
                product_id=999,
                discount_percent=10,
            )

    async def test_counts_recipients(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)
        await CrmService.get_or_create_profile(1, 222)

        broadcast = await BroadcastService.create_broadcast(
            shop_id=1,
            product_id=1,
            discount_percent=10,
        )
        assert broadcast.recipients_count == 2


class TestSendBroadcast:

    async def test_sends_to_all_recipients(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)
        await CrmService.get_or_create_profile(1, 222)

        broadcast = await BroadcastService.create_broadcast(
            shop_id=1,
            product_id=1,
            discount_percent=15,
        )

        mock_bot = AsyncMock()
        result = await BroadcastService.send_broadcast(1, broadcast.id, mock_bot)

        assert result["ok"] is True
        assert result["sent"] == 2
        assert result["failed"] == 0
        assert mock_bot.send_message.call_count == 2

    async def test_already_sent(self, db_session, seed_data):
        broadcast = await BroadcastService.create_broadcast(
            shop_id=1,
            product_id=1,
            discount_percent=10,
        )

        mock_bot = AsyncMock()
        await BroadcastService.send_broadcast(1, broadcast.id, mock_bot)

        result = await BroadcastService.send_broadcast(1, broadcast.id, mock_bot)
        assert result["ok"] is False

    async def test_not_found(self, db_session, seed_data):
        mock_bot = AsyncMock()
        result = await BroadcastService.send_broadcast(1, 999, mock_bot)
        assert result["ok"] is False

    async def test_creates_offers(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)

        broadcast = await BroadcastService.create_broadcast(
            shop_id=1,
            product_id=1,
            discount_percent=20,
        )

        mock_bot = AsyncMock()
        await BroadcastService.send_broadcast(1, broadcast.id, mock_bot)

        from app.services.offer_service import OfferService
        offers = await OfferService.get_user_offers(1, 111)
        assert len(offers) == 1
        assert offers[0]["discount_percent"] == 20

    async def test_handles_send_failure(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)

        broadcast = await BroadcastService.create_broadcast(
            shop_id=1,
            product_id=1,
            discount_percent=10,
        )

        mock_bot = AsyncMock()
        mock_bot.send_message.side_effect = Exception("Blocked")

        result = await BroadcastService.send_broadcast(1, broadcast.id, mock_bot)
        assert result["ok"] is True
        assert result["sent"] == 0
        assert result["failed"] == 1


class TestGetBroadcasts:

    async def test_empty(self, db_session, seed_data):
        result = await BroadcastService.get_broadcasts(1)
        assert result["broadcasts"] == []
        assert result["total"] == 0

    async def test_returns_broadcasts(self, db_session, seed_data):
        await BroadcastService.create_broadcast(1, 1, 10)
        await BroadcastService.create_broadcast(1, 2, 15)

        result = await BroadcastService.get_broadcasts(1)
        assert result["total"] == 2


class TestGetBroadcast:

    async def test_returns_broadcast(self, db_session, seed_data):
        broadcast = await BroadcastService.create_broadcast(1, 1, 10)

        result = await BroadcastService.get_broadcast(1, broadcast.id)
        assert result is not None
        assert result["product_name"] == "Кашемир"

    async def test_wrong_shop(self, db_session, seed_data):
        broadcast = await BroadcastService.create_broadcast(1, 1, 10)

        result = await BroadcastService.get_broadcast(999, broadcast.id)
        assert result is None

    async def test_not_found(self, db_session, seed_data):
        result = await BroadcastService.get_broadcast(1, 999)
        assert result is None
