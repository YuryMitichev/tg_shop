from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Chat, Message, User


def make_message(text=None, user_id=111, chat_id=1):
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.message_id = 1
    msg.from_user = User(id=user_id, is_bot=False, first_name="Test")
    msg.chat = Chat(id=chat_id, type="private")
    msg.date = datetime.now()
    msg.photo = None
    msg.bot = MagicMock()
    msg.answer = AsyncMock(return_value=MagicMock(message_id=2))
    msg.delete = AsyncMock()
    msg.bot.send_message = AsyncMock(return_value=MagicMock(message_id=2))
    msg.bot.edit_message_text = AsyncMock()
    msg.bot.delete_message = AsyncMock()
    return msg


def make_callback(data=None, user_id=111, chat_id=1):
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = User(id=user_id, is_bot=False, first_name="Test")
    cb.message = MagicMock(spec=Message)
    cb.message.chat = Chat(id=chat_id, type="private")
    cb.message.message_id = 1
    cb.message.photo = None
    cb.message.edit_text = AsyncMock()
    cb.message.delete = AsyncMock()
    cb.message.answer = AsyncMock(return_value=MagicMock(message_id=3))
    cb.message.answer_photo = AsyncMock(return_value=MagicMock(message_id=3))
    cb.message.edit_media = AsyncMock()
    cb.bot = MagicMock()
    cb.bot.send_message = AsyncMock(return_value=MagicMock(message_id=3))
    cb.answer = AsyncMock()
    return cb


def make_state(data=None):
    state = MagicMock(spec=FSMContext)
    _data = dict(data or {})
    state.get_data = AsyncMock(return_value=_data)
    state.update_data = AsyncMock(side_effect=lambda **kw: _data.update(kw))
    state.clear = AsyncMock()
    state.set_state = AsyncMock()
    return state


class TestStartHandler:

    async def test_cmd_start_sends_welcome(self, db_session, seed_data):
        from app.bot.handlers.start import setup_router

        router = setup_router()
        handler = router.message.handlers[0].callback

        msg = make_message(text="/start")
        state = make_state()

        with patch("app.bot.handlers.start.settings") as mock_settings:
            mock_settings.webapp_enabled = False
            await handler(msg, state)

        msg.answer.assert_called_once()
        call_kwargs = msg.answer.call_args
        assert "Добро пожаловать" in call_kwargs.kwargs["text"]


class TestCatalogHandler:

    async def test_open_catalog_msg(self, db_session, seed_data):
        from app.bot.handlers.catalog import setup_router

        router = setup_router()
        handler = router.message.handlers[0].callback

        msg = make_message(text="🛍 Каталог")
        state = make_state()

        await handler(msg, state)

        msg.bot.send_message.assert_called_once()
        sent_text = msg.bot.send_message.call_args.kwargs["text"]
        assert "Каталог" in sent_text


class TestCartHandler:

    async def test_open_cart_empty(self, db_session, seed_data):
        from app.bot.handlers.cart import setup_router

        router = setup_router()
        handler = router.message.handlers[0].callback

        msg = make_message(text="🛒 Корзина")
        state = make_state()

        await handler(msg, state)

        msg.bot.send_message.assert_called_once()
        sent_text = msg.bot.send_message.call_args.kwargs["text"]
        assert "Корзина пуста" in sent_text

    async def test_open_cart_with_items(self, db_session, seed_data):
        from app.bot.handlers.cart import setup_router
        from app.services.cart_service import CartService

        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=2)

        router = setup_router()
        handler = router.message.handlers[0].callback

        msg = make_message(text="🛒 Корзина", user_id=111)
        state = make_state()

        await handler(msg, state)

        sent_text = msg.bot.send_message.call_args.kwargs["text"]
        assert "Кашемир" in sent_text
        assert "Итого" in sent_text

    async def test_increase_quantity(self, db_session, seed_data):
        from app.bot.handlers.cart import setup_router
        from app.services.cart_service import CartService

        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)

        router = setup_router()
        inc_handler = router.callback_query.handlers[1].callback

        cb = make_callback(data="cart_inc:1", user_id=111)
        cb.message.edit_text = AsyncMock()

        await inc_handler(cb)

        cb.message.edit_text.assert_called_once()
        items = await CartService.get_items(1, 111)
        assert items[0]["quantity"] == 2

    async def test_decrease_quantity(self, db_session, seed_data):
        from app.bot.handlers.cart import setup_router
        from app.services.cart_service import CartService

        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=3)

        router = setup_router()
        dec_handler = router.callback_query.handlers[2].callback

        cb = make_callback(data="cart_dec:1", user_id=111)
        cb.message.edit_text = AsyncMock()

        await dec_handler(cb)

        items = await CartService.get_items(1, 111)
        assert items[0]["quantity"] == 2

    async def test_remove_item(self, db_session, seed_data):
        from app.bot.handlers.cart import setup_router
        from app.services.cart_service import CartService

        await CartService.add_item(1, 111, product_id=1, variant_id=1, quantity=1)

        router = setup_router()
        remove_handler = router.callback_query.handlers[3].callback

        cb = make_callback(data="cart_remove:1", user_id=111)
        cb.message.edit_text = AsyncMock()

        await remove_handler(cb)

        items = await CartService.get_items(1, 111)
        assert len(items) == 0


class TestInfoHandler:

    async def test_delivery_message(self, db_session, seed_data):
        from app.bot.handlers.info import setup_router

        router = setup_router()
        handler = router.message.handlers[0].callback

        msg = make_message(text="🚚 Доставка")
        state = make_state()

        await handler(msg, state)

        msg.bot.send_message.assert_called_once()
        sent_text = msg.bot.send_message.call_args.kwargs["text"]
        assert "Доставка" in sent_text

    async def test_payment_message(self, db_session, seed_data):
        from app.bot.handlers.info import setup_router

        router = setup_router()
        handlers = router.message.handlers
        payment_handler = handlers[1].callback

        msg = make_message(text="💳 Оплата")
        state = make_state()

        await payment_handler(msg, state)

        msg.bot.send_message.assert_called_once()
        sent_text = msg.bot.send_message.call_args.kwargs["text"]
        assert "Оплата" in sent_text


class TestMenuCallback:

    async def test_menu_callback(self, db_session, seed_data):
        from app.bot.handlers.menu import setup_router

        router = setup_router()
        handler = router.callback_query.handlers[0].callback

        cb = make_callback(data="menu")
        state = make_state()

        await handler(cb, state)

        state.clear.assert_called_once()
        cb.message.edit_text.assert_called_once()
        sent_text = cb.message.edit_text.call_args.args[0]
        assert "Главное меню" in sent_text
        cb.answer.assert_called_once()
