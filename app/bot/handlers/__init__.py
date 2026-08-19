from aiogram import Router


def create_main_router() -> Router:
    from .start import setup_router as setup_start
    from .menu import setup_router as setup_menu
    from .order import setup_router as setup_order
    from .info import setup_router as setup_info
    from .admin import setup_router as setup_admin
    from .catalog import setup_router as setup_catalog
    from .product import setup_router as setup_product
    from .orders import setup_router as setup_orders
    from .cart import setup_router as setup_cart
    from .channel_import import setup_router as setup_channel_import

    router = Router()
    router.include_router(setup_start())
    router.include_router(setup_menu())
    router.include_router(setup_order())
    router.include_router(setup_info())
    router.include_router(setup_channel_import())
    router.include_router(setup_admin())
    router.include_router(setup_catalog())
    router.include_router(setup_product())
    router.include_router(setup_orders())
    router.include_router(setup_cart())
    return router
