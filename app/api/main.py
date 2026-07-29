from fastapi import FastAPI

from app.api.routes.payments import router as payments_router


def create_app() -> FastAPI:
    app = FastAPI(title="TG Shop API")

    app.include_router(payments_router, prefix="/payments", tags=["payments"])

    return app


app = create_app()
