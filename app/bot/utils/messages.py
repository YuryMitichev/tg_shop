from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

LAST_MSG_KEY = "last_msg_id"


async def delete_user_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def show_screen(
    message: Message,
    state: FSMContext,
    text: str,
    reply_markup=None,
) -> None:
    """
    Удаляет сообщение пользователя (нажатие reply-кнопки)
    и обновляет последнее сообщение бота (edit_text).
    Если редактирование не получается — удаляет старое и шлёт новое.
    """

    await delete_user_message(message)

    data = await state.get_data()
    last_msg_id = data.get(LAST_MSG_KEY)

    if last_msg_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=last_msg_id,
                text=text,
                reply_markup=reply_markup,
            )
            return
        except TelegramBadRequest:
            try:
                await message.bot.delete_message(message.chat.id, last_msg_id)
            except TelegramBadRequest:
                pass

    new_msg = await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        reply_markup=reply_markup,
    )
    await state.update_data(**{LAST_MSG_KEY: new_msg.message_id})


async def track_message(state: FSMContext, message: Message) -> None:
    await state.update_data(**{LAST_MSG_KEY: message.message_id})


async def replace_with_text(
    callback_message: Message,
    bot,
    chat_id: int,
    state: FSMContext,
    text: str,
    reply_markup=None,
) -> Message:
    """
    Заменяет сообщение (фото → текст или текст → текст).
    Если было фото — удаляет и шлёт новое текстовое.
    Возвращает новое сообщение и запоминает его в state.
    """

    if callback_message.photo:
        try:
            await callback_message.delete()
        except TelegramBadRequest:
            pass
        new_msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        await state.update_data(**{LAST_MSG_KEY: new_msg.message_id})
        return new_msg
    else:
        try:
            await callback_message.edit_text(text, reply_markup=reply_markup)
            return callback_message
        except TelegramBadRequest:
            new_msg = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )
            await state.update_data(**{LAST_MSG_KEY: new_msg.message_id})
            return new_msg
