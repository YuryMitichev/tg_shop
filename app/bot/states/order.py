from aiogram.fsm.state import State, StatesGroup


class OrderState(StatesGroup):
    waiting_full_name = State()
    waiting_phone = State()
    waiting_address = State()
    waiting_comment = State()
    waiting_receipt = State()
