from aiogram import Router

from .start import router as start_router
from .menu import router as menu_router
from .order import router as order_router
from .info import router as info_router
from .admin import router as admin_router


def create_main_router() -> Router:
    """Создаёт новый Router с подключёнными обработчиками.

    Используется фабрика, потому что aiogram 3 не позволяет
    подключать один и тот же Router к нескольким Dispatcher.
    """
    from .catalog import router as catalog_router
    from .product import router as product_router
    from .orders import router as orders_router
    from .cart import router as cart_router

    router = Router()

    router.include_router(start_router)
    router.include_router(menu_router)
    router.include_router(order_router)
    router.include_router(info_router)
    router.include_router(admin_router)
    router.include_router(catalog_router)
    router.include_router(product_router)
    router.include_router(orders_router)
    router.include_router(cart_router)

    return router
