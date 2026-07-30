from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes.payments import router as payments_router
from app.api.routes.shop import router as shop_router


def create_app() -> FastAPI:
    app = FastAPI(title="TG Shop API")

    app.include_router(payments_router, prefix="/payments", tags=["payments"])
    app.include_router(shop_router, prefix="/api/shop", tags=["shop"])

    static_dir = Path(__file__).parent / "static"

    if static_dir.exists():
        app.mount(
            "/app",
            StaticFiles(directory=str(static_dir), html=True),
            name="webapp",
        )

    return app


app = create_app()
