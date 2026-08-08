import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.admin_auth import require_super_admin
from app.api.rate_limit import limiter
from app.bot.bot import start_shop_bot, stop_shop_bot, restart_shop_bot
from app.services.shop_service import ShopService
from app.services.offer_agreement_service import OfferAgreementService

router = APIRouter()
logger = logging.getLogger(__name__)


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
