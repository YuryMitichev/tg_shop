from aiogram.fsm.state import State, StatesGroup


class CatalogState(StatesGroup):
    category_id = State()
    product_id = State()
    variant_id = State()