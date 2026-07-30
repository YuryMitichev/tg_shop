from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.main_menu import get_reply_keyboard
from app.bot.utils.messages import track_message
from app.services.message_service import MessageService

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):

    await state.clear()

    text = await MessageService.get("welcome")

    msg = await message.answer(
        text=text,
        reply_markup=get_reply_keyboard(),
    )

    await track_message(state, msg)
