from app.models.system_message import SystemMessage
from app.services.message_service import MessageService, DEFAULT_MESSAGES


class TestGet:

    async def test_returns_default(self, db_session, seed_data):
        text = await MessageService.get(1, "welcome")
        assert text == DEFAULT_MESSAGES["welcome"]

    async def test_returns_overridden(self, db_session, seed_data):
        async with db_session() as session:
            session.add(SystemMessage(shop_id=1, key="welcome", content="Привет!"))
            await session.commit()

        text = await MessageService.get(1, "welcome")
        assert text == "Привет!"

    async def test_unknown_key_returns_empty(self, db_session, seed_data):
        text = await MessageService.get(1, "nonexistent")
        assert text == ""


class TestGetAll:

    async def test_returns_all_defaults(self, db_session, seed_data):
        messages = await MessageService.get_all(1)
        assert len(messages) == len(DEFAULT_MESSAGES)
        keys = [m["key"] for m in messages]
        assert "welcome" in keys

    async def test_marks_overrides(self, db_session, seed_data):
        async with db_session() as session:
            session.add(SystemMessage(shop_id=1, key="menu", content="Custom menu"))
            await session.commit()

        messages = await MessageService.get_all(1)
        menu = next(m for m in messages if m["key"] == "menu")
        assert menu["content"] == "Custom menu"
        assert menu["is_default"] is False

    async def test_default_flag_true_for_unmodified(self, db_session, seed_data):
        messages = await MessageService.get_all(1)
        welcome = next(m for m in messages if m["key"] == "welcome")
        assert welcome["is_default"] is True


class TestGetOne:

    async def test_returns_message(self, db_session, seed_data):
        msg = await MessageService.get_one(1, "welcome")
        assert msg is not None
        assert msg["key"] == "welcome"
        assert msg["is_default"] is True

    async def test_returns_none_for_unknown_key(self, db_session, seed_data):
        msg = await MessageService.get_one(1, "nonexistent")
        assert msg is None

    async def test_shows_override(self, db_session, seed_data):
        async with db_session() as session:
            session.add(SystemMessage(shop_id=1, key="payment", content="Нал только"))
            await session.commit()

        msg = await MessageService.get_one(1, "payment")
        assert msg["content"] == "Нал только"
        assert msg["is_default"] is False


class TestUpdate:

    async def test_creates_new(self, db_session, seed_data):
        await MessageService.update(1, "welcome", "Новый текст")

        text = await MessageService.get(1, "welcome")
        assert text == "Новый текст"

    async def test_updates_existing(self, db_session, seed_data):
        await MessageService.update(1, "menu", "Версия 1")
        await MessageService.update(1, "menu", "Версия 2")

        text = await MessageService.get(1, "menu")
        assert text == "Версия 2"


class TestReset:

    async def test_resets_to_default(self, db_session, seed_data):
        await MessageService.update(1, "welcome", "Кастом")
        await MessageService.reset(1, "welcome")

        text = await MessageService.get(1, "welcome")
        assert text == DEFAULT_MESSAGES["welcome"]

    async def test_reset_nonexistent_no_error(self, db_session, seed_data):
        await MessageService.reset(1, "welcome")

        text = await MessageService.get(1, "welcome")
        assert text == DEFAULT_MESSAGES["welcome"]
