from sqlalchemy import select

from app.database.db import async_session
from app.models.system_message import SystemMessage

DEFAULT_MESSAGES = {
    "welcome": (
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Рады видеть вас в нашем магазине.\n\n"
        "Выберите интересующий раздел — кнопки внизу."
    ),
    "menu": "👋 <b>Главное меню</b>\n\nВыберите раздел — кнопки внизу.",
    "catalog": "<b>🛍 Каталог</b>\n\nВыберите категорию.",
    "cart_empty": (
        "🛒 <b>Корзина пуста</b>\n\n"
        "Добавьте товары из каталога."
    ),
    "checkout_name": "📝 <b>Оформление заказа</b>\n\nКак к вам обращаться? Напишите имя и фамилию.",
    "checkout_phone": "📞 Укажите номер телефона для связи.",
    "checkout_comment": (
        "💬 Добавьте комментарий к заказу (пожелания, удобное время и т.д.).\n\n"
        "Отправьте «-», чтобы пропустить."
    ),
    "delivery": (
        "🚚 <b>Доставка</b>\n\n"
        "Доставляем по России курьерской службой и Почтой России.\n"
        "Точную стоимость и сроки уточним при оформлении заказа — "
        "они зависят от региона."
    ),
    "payment": (
        "💳 <b>Оплата</b>\n\n"
        "Оплата переводом по СБП или на карту — реквизиты пришлёт "
        "менеджер после оформления заказа."
    ),
}

MESSAGE_LABELS = {
    "welcome": "👋 Приветствие (/start)",
    "menu": "🏠 Главное меню",
    "catalog": "🛍 Каталог",
    "cart_empty": "🛒 Пустая корзина",
    "checkout_name": "📝 Запрос имени",
    "checkout_phone": "📞 Запрос телефона",
    "checkout_comment": "💬 Запрос комментария",
    "delivery": "🚚 Доставка",
    "payment": "💳 Оплата",
}


class MessageService:
    """
    Управление редактируемыми системными сообщениями.
    Если сообщение не найдено в БД — возвращает дефолт.
    """

    @staticmethod
    async def get(shop_id: int, key: str) -> str:
        """Получить текст сообщения по ключу."""
        async with async_session() as session:
            result = await session.execute(
                select(SystemMessage.content).where(
                    SystemMessage.shop_id == shop_id,
                    SystemMessage.key == key,
                )
            )
            content = result.scalar_one_or_none()

        return content if content is not None else DEFAULT_MESSAGES.get(key, "")

    @staticmethod
    async def get_all(shop_id: int) -> list[dict]:
        """Все сообщения с метаданными для админки."""
        async with async_session() as session:
            result = await session.execute(
                select(SystemMessage)
                .where(SystemMessage.shop_id == shop_id)
                .order_by(SystemMessage.key)
            )
            db_messages = {m.key: m.content for m in result.scalars().all()}

        messages = []
        for key in DEFAULT_MESSAGES:
            messages.append({
                "key": key,
                "label": MESSAGE_LABELS.get(key, key),
                "content": db_messages.get(key, DEFAULT_MESSAGES[key]),
                "is_default": key not in db_messages,
            })

        return messages

    @staticmethod
    async def get_one(shop_id: int, key: str) -> dict | None:
        """Одно сообщение для редактирования."""
        if key not in DEFAULT_MESSAGES:
            return None

        async with async_session() as session:
            result = await session.execute(
                select(SystemMessage.content).where(
                    SystemMessage.shop_id == shop_id,
                    SystemMessage.key == key,
                )
            )
            content = result.scalar_one_or_none()

        return {
            "key": key,
            "label": MESSAGE_LABELS.get(key, key),
            "content": content if content is not None else DEFAULT_MESSAGES[key],
            "is_default": content is None,
        }

    @staticmethod
    async def update(shop_id: int, key: str, content: str) -> None:
        """Обновить или создать сообщение."""
        async with async_session() as session:
            result = await session.execute(
                select(SystemMessage).where(
                    SystemMessage.shop_id == shop_id,
                    SystemMessage.key == key,
                )
            )
            msg = result.scalar_one_or_none()

            if msg:
                msg.content = content
            else:
                session.add(SystemMessage(shop_id=shop_id, key=key, content=content))

            await session.commit()

    @staticmethod
    async def reset(shop_id: int, key: str) -> None:
        """Сбросить сообщение к значению по умолчанию."""
        async with async_session() as session:
            result = await session.execute(
                select(SystemMessage).where(
                    SystemMessage.shop_id == shop_id,
                    SystemMessage.key == key,
                )
            )
            msg = result.scalar_one_or_none()

            if msg:
                await session.delete(msg)
                await session.commit()
