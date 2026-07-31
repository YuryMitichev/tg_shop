from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes.payments import router as payments_router
from app.api.routes.shop import router as shop_router
from app.api.routes.admin import router as admin_router


def create_app() -> FastAPI:
    app = FastAPI(title="TG Shop API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(payments_router, prefix="/payments", tags=["payments"])
    app.include_router(shop_router, prefix="/api/shop", tags=["shop"])
    app.include_router(admin_router, prefix="/api/admin", tags=["admin"])

    static_dir = Path(__file__).parent / "static"

    if static_dir.exists():
        app.mount(
            "/app",
            StaticFiles(directory=str(static_dir), html=True),
            name="webapp",
        )

    return app


app = create_app()
