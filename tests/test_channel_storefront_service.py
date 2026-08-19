from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

from app.core.config import settings
from app.models.channel_import import ChannelConnection
from app.services.channel_import_service import ChannelImportService
from app.services.channel_storefront_service import ChannelStorefrontService


class _FakeBot:
    def __init__(self, *, has_main_web_app: bool = True, can_edit_messages: bool = True):
        self.has_main_web_app = has_main_web_app
        self.can_edit_messages = can_edit_messages
        self.sent = []
        self.edited = []
        self.pinned = []
        self.next_message_id = 901

    async def get_me(self):
        return SimpleNamespace(
            id=77,
            username="test_shop_bot",
            has_main_web_app=self.has_main_web_app,
        )

    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(
            status="administrator",
            can_edit_messages=self.can_edit_messages,
        )

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=self.next_message_id)

    async def edit_message_text(self, **kwargs):
        self.edited.append(kwargs)
        return True

    async def pin_chat_message(self, **kwargs):
        self.pinned.append(kwargs)
        return True


class _DeletedMessageBot(_FakeBot):
    async def edit_message_text(self, **kwargs):
        self.edited.append(kwargs)
        raise TelegramBadRequest(
            method=SimpleNamespace(),
            message="Bad Request: message to edit not found",
        )


async def _connect() -> None:
    await ChannelImportService.connect_channel(
        1,
        channel_id=-100777,
        channel_title="Storefront channel",
        channel_username="storefront_channel",
        connected_by=1,
    )


def _enable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "channel_product_buttons_enabled", True)
    monkeypatch.setattr(settings, "channel_product_buttons_pilot_shop_id", None)


@pytest.mark.asyncio
async def test_storefront_message_is_created_pinned_and_reused(
    db_session, seed_data, monkeypatch
):
    _enable(monkeypatch)
    await _connect()
    bot = _FakeBot()

    first = await ChannelStorefrontService.sync(1, bot=bot)
    second = await ChannelStorefrontService.sync(1, bot=bot)

    assert first["status"] == "active"
    assert second["status"] == "active"
    assert second["message_id"] == 901
    assert len(bot.sent) == 1
    assert len(bot.edited) == 1
    assert len(bot.pinned) == 2
    button = bot.sent[0]["reply_markup"].model_dump(
        mode="json", exclude_none=True
    )["inline_keyboard"][0][0]
    assert button["text"] == "🛍 Открыть магазин"
    assert button["style"] == "success"
    assert button["url"].endswith("?startapp=shop_1")


@pytest.mark.asyncio
async def test_storefront_missing_message_is_recreated(
    db_session, seed_data, monkeypatch
):
    _enable(monkeypatch)
    await _connect()
    async with db_session() as session:
        connection = (
            await session.execute(select(ChannelConnection).where(ChannelConnection.shop_id == 1))
        ).scalar_one()
        connection.storefront_message_id = 800
        await session.commit()

    bot = _DeletedMessageBot()
    result = await ChannelStorefrontService.sync(1, bot=bot)

    assert result["status"] == "active"
    assert result["message_id"] == 901
    assert len(bot.edited) == 1
    assert len(bot.sent) == 1
    assert bot.pinned[0]["message_id"] == 901


@pytest.mark.asyncio
async def test_storefront_missing_main_app_records_recoverable_error(
    db_session, seed_data, monkeypatch
):
    _enable(monkeypatch)
    await _connect()

    with pytest.raises(ValueError, match="Main Mini App"):
        await ChannelStorefrontService.sync(1, bot=_FakeBot(has_main_web_app=False))

    result = await ChannelStorefrontService.status(1)
    assert result["status"] == "needs_action"
    assert result["error_code"] == "main_app_missing"


@pytest.mark.asyncio
async def test_storefront_missing_edit_permission_does_not_publish(
    db_session, seed_data, monkeypatch
):
    _enable(monkeypatch)
    await _connect()
    bot = _FakeBot(can_edit_messages=False)

    with pytest.raises(ValueError, match="редактировать и закреплять"):
        await ChannelStorefrontService.sync(1, bot=bot)

    assert bot.sent == []
    result = await ChannelStorefrontService.status(1)
    assert result["status"] == "needs_action"
    assert result["error_code"] == "edit_permission_required"
