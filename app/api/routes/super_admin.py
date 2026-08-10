import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.admin_auth import require_super_admin
from app.api.rate_limit import limiter
from app.bot.bot import start_shop_bot, stop_shop_bot, restart_shop_bot
from app.database.db import async_session
from app.models.shop import Shop
from app.models.subscription import Subscription, SubscriptionPlan
from app.services.offer_agreement_service import OfferAgreementService
from app.services.shop_service import ShopService
from app.services.subscription_service import SubscriptionService

router = APIRouter()
logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==========================
# Pydantic схемы
# ==========================

class CreateShopRequest(BaseModel):
    name: str
    bot_token: str
    owner_telegram_id: int


class UpdateShopRequest(BaseModel):
    name: str | None = None
    bot_token: str | None = None
    owner_telegram_id: int | None = None
    is_active: bool | None = None


class ExtendSubscriptionBody(BaseModel):
    add_days: int


class CreatePlanBody(BaseModel):
    name: str
    description: str | None = None
    price: float
    duration_days: int
    features: list[str] = []


class UpdatePlanBody(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    duration_days: int | None = None
    is_active: bool | None = None
    features: list[str] | None = None


# ==========================
# Эндпоинты
# ==========================

@router.get("/shops")
async def list_shops(
    active_only: bool = False,
    _admin: dict = Depends(require_super_admin),
):
    shops = await ShopService.get_all(active_only=active_only)
    return {"shops": shops}


@router.post("/shops")
@limiter.limit("5/minute")
async def create_shop(
    request: Request,
    body: CreateShopRequest,
    _admin: dict = Depends(require_super_admin),
):
    existing = await ShopService.get_by_bot_token(body.bot_token)
    if existing:
        raise HTTPException(status_code=409, detail="Магазин с таким bot_token уже существует")

    shop = await ShopService.create(
        name=body.name,
        bot_token=body.bot_token,
        owner_telegram_id=body.owner_telegram_id,
    )

    try:
        await start_shop_bot(shop["id"])
    except Exception:
        logger.exception("Не удалось запустить бота для магазина %d", shop["id"])

    return shop


@router.get("/shops/{shop_id}")
async def get_shop(
    shop_id: int,
    _admin: dict = Depends(require_super_admin),
):
    shop = await ShopService.get(shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="Магазин не найден")
    return shop


@router.patch("/shops/{shop_id}")
async def update_shop(
    shop_id: int,
    body: UpdateShopRequest,
    _admin: dict = Depends(require_super_admin),
):
    if body.bot_token is not None:
        existing = await ShopService.get_by_bot_token(body.bot_token)
        if existing and existing["id"] != shop_id:
            raise HTTPException(status_code=409, detail="Этот bot_token уже используется другим магазином")

    shop = await ShopService.update(
        shop_id,
        name=body.name,
        bot_token=body.bot_token,
        owner_telegram_id=body.owner_telegram_id,
        is_active=body.is_active,
    )
    if shop is None:
        raise HTTPException(status_code=404, detail="Магазин не найден")

    token_changed = body.bot_token is not None
    deactivated = body.is_active is False

    if deactivated and not token_changed:
        await stop_shop_bot(shop_id)
    elif token_changed:
        await restart_shop_bot(shop_id)

    return shop


@router.delete("/shops/{shop_id}")
async def delete_shop(
    shop_id: int,
    _admin: dict = Depends(require_super_admin),
):
    if shop_id == 1:
        raise HTTPException(status_code=400, detail="Нельзя удалить магазин по умолчанию")

    await stop_shop_bot(shop_id)

    ok = await ShopService.delete(shop_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Магазин не найден")
    return {"ok": True}


# ==========================
# Оферта — записи о принятии
# ==========================

@router.get("/offer/acceptances")
async def list_offer_acceptances(_admin: dict = Depends(require_super_admin)):
    return {"acceptances": await OfferAgreementService.list_acceptances()}


# ==========================
# Платформенный дашборд
# ==========================

@router.get("/dashboard")
async def platform_dashboard(_admin: dict = Depends(require_super_admin)):
    now = _utcnow()
    thirty_days_ago = now - timedelta(days=30)

    async with async_session() as session:
        total_shops = await session.scalar(
            select(func.count()).select_from(Shop)
        )

        new_shops_30d = await session.scalar(
            select(func.count()).select_from(Shop).where(Shop.created_at >= thirty_days_ago)
        )

        sub_stats = (
            await session.execute(
                select(
                    func.count().label("total"),
                    func.count().filter(
                        Subscription.status.in_(["trial", "active"]),
                        Subscription.expires_at > now,
                    ).label("active"),
                    func.count().filter(
                        Subscription.status == "trial",
                        Subscription.expires_at > now,
                    ).label("trial"),
                ).select_from(Subscription)
            )
        ).one()

        revenue = await session.scalar(
            select(func.coalesce(func.sum(SubscriptionPlan.price), 0))
            .join(Subscription, Subscription.plan_id == SubscriptionPlan.id)
            .where(
                SubscriptionPlan.is_trial == False,  # noqa: E712
                Subscription.external_payment_id.is_not(None),
            )
        )

    active_subs = sub_stats.active or 0
    total_subs = sub_stats.total or 0

    return {
        "total_shops": total_shops or 0,
        "active_shops": active_subs,
        "trial_shops": sub_stats.trial or 0,
        "expired_shops": total_subs - active_subs,
        "new_shops_30d": new_shops_30d or 0,
        "total_revenue": revenue or 0,
    }


# ==========================
# Подписки
# ==========================

@router.get("/subscriptions")
async def list_subscriptions(
    status: str | None = None,
    _admin: dict = Depends(require_super_admin),
):
    now = _utcnow()

    async with async_session() as session:
        query = (
            select(
                Subscription.id,
                Subscription.shop_id,
                Subscription.status,
                Subscription.started_at,
                Subscription.expires_at,
                Subscription.external_payment_id,
                Shop.name.label("shop_name"),
                SubscriptionPlan.name.label("plan_name"),
                SubscriptionPlan.price.label("plan_price"),
                SubscriptionPlan.is_trial.label("is_trial"),
            )
            .join(Shop, Subscription.shop_id == Shop.id)
            .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
            .order_by(Subscription.expires_at.desc())
        )

        if status == "active":
            query = query.where(
                Subscription.status.in_(["trial", "active"]),
                Subscription.expires_at > now,
            )
        elif status == "expired":
            query = query.where(
                (Subscription.status == "expired") | (Subscription.expires_at < now)
            )
        elif status == "trial":
            query = query.where(
                Subscription.status == "trial",
                Subscription.expires_at > now,
            )

        result = await session.execute(query)
        rows = result.all()

    return {
        "subscriptions": [
            {
                "id": r.id,
                "shop_id": r.shop_id,
                "shop_name": r.shop_name,
                "plan_name": r.plan_name,
                "plan_price": r.plan_price,
                "is_trial": r.is_trial,
                "status": "expired" if r.expires_at < now else r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "expires_at": r.expires_at.isoformat(),
                "external_payment_id": r.external_payment_id,
            }
            for r in rows
        ]
    }


@router.patch("/subscriptions/{shop_id}")
async def extend_subscription(
    shop_id: int,
    body: ExtendSubscriptionBody,
    _admin: dict = Depends(require_super_admin),
):
    now = _utcnow()

    async with async_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.shop_id == shop_id)
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            raise HTTPException(status_code=404, detail="Подписка не найдена")

        base = max(now, sub.expires_at)
        sub.expires_at = base + timedelta(days=body.add_days)
        if sub.status in ("expired", "cancelled"):
            sub.status = "active"

        await session.commit()
        SubscriptionService._active_cache.invalidate(shop_id)

        logger.info(
            "Подписка магазина %d продлена на %d дней до %s",
            shop_id, body.add_days, sub.expires_at,
        )

        return {
            "shop_id": shop_id,
            "status": sub.status,
            "expires_at": sub.expires_at.isoformat(),
        }


# ==========================
# Тарифы
# ==========================

@router.get("/plans")
async def list_all_plans(_admin: dict = Depends(require_super_admin)):
    async with async_session() as session:
        result = await session.execute(
            select(SubscriptionPlan).order_by(SubscriptionPlan.price)
        )
        plans = result.scalars().all()

    return {
        "plans": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": p.price,
                "duration_days": p.duration_days,
                "is_trial": p.is_trial,
                "is_active": p.is_active,
                "features": json.loads(p.features) if p.features else [],
            }
            for p in plans
        ]
    }


@router.post("/plans")
async def create_plan(
    body: CreatePlanBody,
    _admin: dict = Depends(require_super_admin),
):
    async with async_session() as session:
        plan = SubscriptionPlan(
            name=body.name,
            description=body.description,
            price=body.price,
            duration_days=body.duration_days,
            is_trial=False,
            is_active=True,
            features=json.dumps(body.features, ensure_ascii=False) if body.features else None,
        )
        session.add(plan)
        await session.commit()
        await session.refresh(plan)

    logger.info("Создан тариф: %s (id=%d)", body.name, plan.id)
    return {"id": plan.id}


@router.patch("/plans/{plan_id}")
async def update_plan(
    plan_id: int,
    body: UpdatePlanBody,
    _admin: dict = Depends(require_super_admin),
):
    async with async_session() as session:
        plan = await session.get(SubscriptionPlan, plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Тариф не найден")

        if body.name is not None:
            plan.name = body.name
        if body.description is not None:
            plan.description = body.description
        if body.price is not None:
            plan.price = body.price
        if body.duration_days is not None:
            plan.duration_days = body.duration_days
        if body.is_active is not None:
            plan.is_active = body.is_active
        if body.features is not None:
            plan.features = json.dumps(body.features, ensure_ascii=False)

        await session.commit()

    logger.info("Тариф %d обновлён", plan_id)
    return {"ok": True}
