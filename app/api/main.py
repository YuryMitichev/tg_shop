import logging

from pathlib import Path

import sentry_sdk

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from sqlalchemy import text

from app.api.admin_auth import SubscriptionExpiredException
from app.api.rate_limit import limiter
from app.api.routes.payments import router as payments_router
from app.api.routes.shop import router as shop_router
from app.api.routes.admin import router as admin_router
from app.api.routes.super_admin import router as super_admin_router
from app.api.routes.subscriptions import router as subscriptions_router
from app.core.config import settings
from app.core.logging import RequestIdMiddleware, setup_logging, get_request_id
from app.database.db import async_session

setup_logging(debug=settings.debug)

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Инициализирует Sentry, если SENTRY_DSN задан."""
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment="production" if not settings.debug else "development",
        traces_sample_rate=0.0,
        send_default_pii=False,
    )
    logger.info("Sentry initialized")


init_sentry()


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

    @app.exception_handler(SubscriptionExpiredException)
    async def subscription_expired_handler(request: Request, exc: SubscriptionExpiredException):
        return JSONResponse(
            status_code=403,
            content={
                "error": "subscription_expired",
                "message": "Продлите подписку, чтобы получить доступ к этому разделу",
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        rid = get_request_id() or "-"
        logger.exception(
            "Unhandled exception on %s %s [request_id=%s]",
            request.method,
            request.url.path,
            rid,
        )
        sentry_sdk.capture_exception(exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера", "request_id": rid},
            headers={"X-Request-Id": rid},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RequestIdMiddleware)

    @app.get("/health")
    async def health_check():
        try:
            async with async_session() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "ok"}
        except Exception:
            logger.exception("Health check failed: database unreachable")
            return Response(
                content='{"status":"error"}',
                status_code=503,
                media_type="application/json",
            )

    @app.get("/api/offer")
    async def get_offer():
        from app.services.offer_agreement_service import get_offer_text, OFFER_VERSION
        return {"text": get_offer_text(), "version": OFFER_VERSION}

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
