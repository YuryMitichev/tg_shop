from aiogram.fsm.state import State, StatesGroup


class AdminProductState(StatesGroup):
    waiting_name = State()
    waiting_description = State()
    waiting_photos = State()
    waiting_variant_volume = State()
    waiting_variant_price = State()
    waiting_variant_burn = State()
    confirm_more_variants = State()


class AdminEditProductState(StatesGroup):
    waiting_new_name = State()
    waiting_new_description = State()
    waiting_add_photo = State()


class AdminCategoryState(StatesGroup):
    waiting_name = State()
    waiting_rename = State()
    waiting_emoji = State()
