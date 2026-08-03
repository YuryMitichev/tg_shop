from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.api.rate_limit import limiter
from app.api.routes.payments import router as payments_router
from app.api.routes.shop import router as shop_router
from app.api.routes.admin import router as admin_router
from app.api.routes.super_admin import router as super_admin_router
from app.api.routes.subscriptions import router as subscriptions_router
from app.core.config import settings


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles с заголовком Cache-Control: no-cache,
    чтобы Telegram WebApp не кешировал старые версии."""

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


def create_app() -> FastAPI:
    app = FastAPI(title="TG Shop API")

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(payments_router, prefix="/payments", tags=["payments"])
    app.include_router(shop_router, prefix="/api/shop", tags=["shop"])
    app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
    app.include_router(super_admin_router, prefix="/api/super-admin", tags=["super-admin"])
    app.include_router(subscriptions_router, prefix="/api/subscriptions", tags=["subscriptions"])

    static_dir = Path(__file__).parent / "static"

    if static_dir.exists():
        app.mount(
            "/app",
            NoCacheStaticFiles(directory=str(static_dir), html=True),
            name="webapp",
        )

    return app


app = create_app()
