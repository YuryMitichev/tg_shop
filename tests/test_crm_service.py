from app.models.user_profile import UserProfile
from app.models.order import Order
from app.services.crm_service import CrmService
from app.services.order_service import OrderService
from app.services.cart_service import CartService


async def _create_order(db_session, tg_id=111, name="Иван Петров", phone="+79991234567"):
    await CartService.add_item(1, tg_id, product_id=1, variant_id=1, quantity=2)
    return await OrderService.create_order(
        shop_id=1,
        telegram_user_id=tg_id,
        full_name=name,
        phone=phone,
        address="Москва, ул. Тестовая, 1",
    )


class TestGetOrCreateProfile:

    async def test_creates_new(self, db_session, seed_data):
        profile = await CrmService.get_or_create_profile(1, 111, username="ivan", first_name="Иван")
        assert profile.id is not None
        assert profile.telegram_user_id == 111
        assert profile.first_name == "Иван"

    async def test_returns_existing(self, db_session, seed_data):
        p1 = await CrmService.get_or_create_profile(1, 111, first_name="Иван")
        p2 = await CrmService.get_or_create_profile(1, 111, first_name="Иван")
        assert p1.id == p2.id

    async def test_updates_stale_fields(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111, username="old_name")
        await CrmService.get_or_create_profile(1, 111, username="new_name")

        async with db_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(UserProfile).where(UserProfile.telegram_user_id == 111))
            profile = result.scalar_one()
            assert profile.username == "new_name"


class TestUpdateLastSeen:

    async def test_updates(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)
        await CrmService.update_last_seen(1, 111)

        async with db_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(UserProfile).where(UserProfile.telegram_user_id == 111))
            profile = result.scalar_one()
            assert profile.last_seen is not None

    async def test_nonexistent_no_error(self, db_session, seed_data):
        await CrmService.update_last_seen(1, 999)


class TestLogMessage:

    async def test_logs_message(self, db_session, seed_data):
        await CrmService.log_message(1, 111, direction="in", text="Привет")

        history = await CrmService.get_communication_history(1, 111)
        assert history["total"] == 1
        assert history["messages"][0]["text"] == "Привет"
        assert history["messages"][0]["direction"] == "in"

    async def test_truncates_long_text(self, db_session, seed_data):
        long_text = "x" * 600
        await CrmService.log_message(1, 111, text=long_text)

        history = await CrmService.get_communication_history(1, 111)
        assert len(history["messages"][0]["text"]) == 500


class TestBackfillFromOrders:

    async def test_creates_profile_from_order(self, db_session, seed_data):
        await _create_order(db_session)

        count = await CrmService.backfill_from_orders(1)
        assert count == 1

    async def test_skips_cancelled_orders(self, db_session, seed_data):
        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)
        result = await OrderService.create_order(1, 111, "Иван", "+7999", "Москва, ул. Тест, 1")
        from app.services.order_admin_service import OrderAdminService
        await OrderAdminService.set_order_status(1, result["order_id"], "cancelled")

        count = await CrmService.backfill_from_orders(1)
        assert count == 0

    async def test_updates_existing_profile(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111, first_name="Старое")
        await _create_order(db_session)

        count = await CrmService.backfill_from_orders(1)
        assert count == 1


class TestGetUsers:

    async def test_empty(self, db_session, seed_data):
        result = await CrmService.get_users(1)
        assert result["users"] == []
        assert result["total"] == 0

    async def test_returns_users_with_stats(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111, first_name="Иван")
        await _create_order(db_session, tg_id=111)

        result = await CrmService.get_users(1)
        assert result["total"] == 1
        user = result["users"][0]
        assert user["first_name"] == "Иван"
        assert user["orders_count"] == 1
        assert user["total_spent"] == 900

    async def test_search_by_name(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111, first_name="Иван")
        await CrmService.get_or_create_profile(1, 222, first_name="Пётр")

        result = await CrmService.get_users(1, search="Иван")
        assert result["total"] == 1
        assert result["users"][0]["first_name"] == "Иван"


class TestGetUserDetail:

    async def test_returns_none_for_nonexistent(self, db_session, seed_data):
        detail = await CrmService.get_user_detail(1, 999)
        assert detail is None

    async def test_returns_detail_with_stats(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111, first_name="Иван")
        await _create_order(db_session, tg_id=111)

        detail = await CrmService.get_user_detail(1, 111)
        assert detail["first_name"] == "Иван"
        assert detail["orders_count"] == 1
        assert len(detail["orders"]) == 1
        assert len(detail["favorite_products"]) == 1


class TestNotesAndTags:

    async def test_update_notes(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)

        ok = await CrmService.update_notes(1, 111, "Важный клиент")
        assert ok is True

        detail = await CrmService.get_user_detail(1, 111)
        assert detail["notes"] == "Важный клиент"

    async def test_update_notes_nonexistent(self, db_session, seed_data):
        ok = await CrmService.update_notes(1, 999, "test")
        assert ok is False

    async def test_add_tag(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)

        await CrmService.add_tag(1, 111, "VIP")
        await CrmService.add_tag(1, 111, "Постоянный")

        detail = await CrmService.get_user_detail(1, 111)
        assert "VIP" in detail["tags"]
        assert "Постоянный" in detail["tags"]

    async def test_add_duplicate_tag(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)
        await CrmService.add_tag(1, 111, "VIP")
        await CrmService.add_tag(1, 111, "VIP")

        detail = await CrmService.get_user_detail(1, 111)
        assert detail["tags"].count("VIP") == 1

    async def test_remove_tag(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)
        await CrmService.add_tag(1, 111, "VIP")
        await CrmService.add_tag(1, 111, "Постоянный")

        await CrmService.remove_tag(1, 111, "VIP")

        detail = await CrmService.get_user_detail(1, 111)
        assert "VIP" not in detail["tags"]
        assert "Постоянный" in detail["tags"]

    async def test_get_all_tags(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)
        await CrmService.get_or_create_profile(1, 222)
        await CrmService.add_tag(1, 111, "VIP")
        await CrmService.add_tag(1, 222, "Новичок")

        tags = await CrmService.get_all_tags(1)
        assert "VIP" in tags
        assert "Новичок" in tags

    async def test_update_phone(self, db_session, seed_data):
        await CrmService.get_or_create_profile(1, 111)

        ok = await CrmService.update_phone(1, 111, "+79990001111")
        assert ok is True

        detail = await CrmService.get_user_detail(1, 111)
        assert detail["phone"] == "+79990001111"
