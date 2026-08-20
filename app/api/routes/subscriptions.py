import re
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.admin_auth import require_admin
from app.api.rate_limit import limiter
from app.core.config import settings
from app.services.platform_settings_service import PlatformSettingsService
from app.services.subscription_service import SubscriptionService
from app.services.subscription_payment_service import SubscriptionPaymentService

router = APIRouter()


class PayRequest(BaseModel):
    plan_id: int = Field(gt=0)


@router.get("/plans")
async def list_plans():
    """Возвращает доступные тарифы подписки."""
    return await SubscriptionService.get_plans()


@router.get("/current")
async def get_current_subscription(
    admin: dict = Depends(require_admin),
):
    """Возвращает текущую подписку магазина."""
    sub = await SubscriptionService.get_active_subscription(admin["shop_id"])
    if sub is None:
        return {"status": "none", "is_active": False}
    return sub


@router.post("/pay")
@limiter.limit("5/minute")
async def create_payment(
    request: Request,
    req: PayRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    admin: dict = Depends(require_admin),
):
    """Создаёт платёж для оплаты подписки через ЮKassa."""
    if not await PlatformSettingsService.is_yookassa_enabled():
        raise HTTPException(status_code=503, detail="ЮKassa не настроена")

    if idempotency_key is not None and not re.fullmatch(r"[A-Za-z0-9._:-]{8,64}", idempotency_key):
        raise HTTPException(status_code=400, detail="Некорректный Idempotency-Key")
    stable_key = idempotency_key or (
        f"auto:{admin['admin_id']}:{int(time.time()) // 600}"
    )

    result = await SubscriptionPaymentService.create_payment(
        shop_id=admin["shop_id"],
        plan_id=req.plan_id,
        idempotency_key=stable_key,
    )

    if result is None:
        raise HTTPException(status_code=500, detail="Не удалось создать платёж")

    return result
