from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.main_menu import get_reply_keyboard
from app.bot.utils.messages import track_message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):

    await state.clear()

    msg = await message.answer(
        text=(
            "👋 <b>Добро пожаловать!</b>\n\n"
            "Рады видеть вас в нашем магазине.\n\n"
            "Выберите интересующий раздел — кнопки внизу."
        ),
        reply_markup=get_reply_keyboard()
    )

    await track_message(state, msg)
