from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.api.routes.shop import get_shop_id
from app.core.config import settings
from app.services.subscription_service import SubscriptionService
from app.services.subscription_payment_service import SubscriptionPaymentService

router = APIRouter()


class PayRequest(BaseModel):
    plan_id: int


@router.get("/plans")
async def list_plans():
    """Возвращает доступные тарифы подписки."""
    return await SubscriptionService.get_plans()


@router.get("/current")
async def get_current_subscription(
    shop_id: int = Depends(get_shop_id),
):
    """Возвращает текущую подписку магазина."""
    sub = await SubscriptionService.get_active_subscription(shop_id)
    if sub is None:
        return {"status": "none", "is_active": False}
    return sub


@router.post("/pay")
async def create_payment(
    req: PayRequest,
    shop_id: int = Depends(get_shop_id),
):
    """Создаёт платёж для оплаты подписки через ЮKassa."""
    if not settings.yookassa_enabled:
        raise HTTPException(status_code=503, detail="ЮKassa не настроена")

    result = await SubscriptionPaymentService.create_payment(
        shop_id=shop_id,
        plan_id=req.plan_id,
    )

    if result is None:
        raise HTTPException(status_code=500, detail="Не удалось создать платёж")

    return result
