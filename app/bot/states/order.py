from aiogram.fsm.state import State, StatesGroup


class OrderState(StatesGroup):
    waiting_receipt_order_id = State()
    waiting_receipt = State()


class ReviewState(StatesGroup):
    waiting_rating = State()
    waiting_text = State()
