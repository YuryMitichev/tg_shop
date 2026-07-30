from aiogram import Router

from .start import router as start_router
from .menu import router as menu_router
from .order import router as order_router
from .info import router as info_router
from .admin import router as admin_router

router = Router()

router.include_router(start_router)
router.include_router(menu_router)
router.include_router(order_router)
router.include_router(info_router)
router.include_router(admin_router)
