from aiogram import Router

from .catalog import router as catalog_router
from .start import router as start_router
from .menu import router as menu_router
from .product import router as product_router
from .cart import router as cart_router
from .order import router as order_router
from .orders import router as orders_router
from .info import router as info_router
from .admin import router as admin_router

router = Router()

router.include_router(start_router)
router.include_router(menu_router)
router.include_router(catalog_router)
router.include_router(product_router)
router.include_router(cart_router)
router.include_router(order_router)
router.include_router(orders_router)
router.include_router(info_router)
router.include_router(admin_router)
