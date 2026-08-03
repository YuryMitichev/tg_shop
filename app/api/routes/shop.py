import aiohttp
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user, get_optional_user
from app.bot.bot import get_bot
from app.core.config import settings
from app.database.db import async_session
from app.models.product import Product
from app.models.product_photo import ProductPhoto
from app.services.catalog_service import CatalogService
from app.services.cart_service import CartService
from app.services.offer_service import OfferService
from app.services.order_payment_service import OrderPaymentService
from app.services.order_service import OrderService
from app.services.promo_service import PromoCodeService
from app.services.review_service import ReviewService
from app.services.shop_service import ShopService
from app.models.shop import AVAILABLE_PRODUCT_ATTRS

router = APIRouter()


async def get_shop_id(x_shop_id: int | None = Header(None, alias="X-Shop-Id")) -> int:
    """Определяет shop_id из заголовка X-Shop-Id (по умолчанию 1)."""
    return x_shop_id or 1


@router.get("/shop-config")
async def get_shop_config(shop_id: int = Depends(get_shop_id)):
    """Конфиг магазина для мини-аппа: включённые характеристики товара и т.д."""
    shop = await ShopService.get(shop_id)
    attrs = shop["product_attrs"] if shop else ["volume"]
    labels = {a["key"]: a["label"] for a in AVAILABLE_PRODUCT_ATTRS}
    return {
        "product_attrs": attrs,
        "attr_labels": {k: labels.get(k, k) for k in attrs},
    }


# ==========================
# Pydantic схемы
# ==========================

class AddToCartRequest(BaseModel):
    product_id: int
    variant_id: int
    quantity: int = 1


class ChangeQuantityRequest(BaseModel):
    delta: int


class CreateOrderRequest(BaseModel):
    full_name: str
    phone: str
    comment: str | None = None
    promo_code: str | None = None
    payment_method: str = "manual"


class ValidatePromoRequest(BaseModel):
    code: str


# ==========================
# Каталог
# ==========================

@router.get("/categories")
async def list_categories(shop_id: int = Depends(get_shop_id)):
    categories = await CatalogService.get_categories(shop_id)
    return categories


@router.get("/products")
async def list_products(
    category_id: int = Query(...),
    user: dict | None = Depends(get_optional_user),
    shop_id: int = Depends(get_shop_id),
):
    sid = user["shop_id"] if user else shop_id
    products = await CatalogService.get_products(sid, category_id)
    tg_id = user.get("id") if user else None

    result = []
    for p in products:
        prices = [v["price"] for v in p["variants"]]
        summary = await ReviewService.get_rating_summary(sid, p["id"])

        has_offer = False
        if tg_id:
            for v in p["variants"]:
                offer = await OfferService.get_best_offer(sid, tg_id, p["id"], v["id"])
                if offer and offer.discount_percent > 0:
                    has_offer = True
                    break

        result.append({
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "price_from": min(prices) if prices else 0,
            "price_to": max(prices) if prices else 0,
            "photo_id": p["photos"][0]["id"] if p.get("photos") else None,
            "rating": summary,
            "has_offer": has_offer,
        })

    return result


@router.get("/products/{product_id}")
async def get_product_detail(
    product_id: int,
    user: dict | None = Depends(get_optional_user),
    shop_id: int = Depends(get_shop_id),
):
    sid = user["shop_id"] if user else shop_id
    product = await CatalogService.get_product(sid, product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    summary = await ReviewService.get_rating_summary(sid, product_id)
    reviews = await ReviewService.get_product_reviews(sid, product_id, limit=10)

    tg_id = user.get("id") if user else None
    if tg_id:
        product["variants"] = await OfferService.apply_to_variants(
            sid, tg_id, product_id, product["variants"]
        )

    return {
        **product,
        "rating": summary,
        "reviews": reviews,
    }


# ==========================
# Фото (прокси через Telegram)
# ==========================

_file_path_cache: dict[str, str] = {}


@router.get("/photo/{photo_id}")
async def get_photo(photo_id: int):
    async with async_session() as session:
        photo = await session.get(ProductPhoto, photo_id)

    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    bot = get_bot(photo.shop_id)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not available")

    file_id = photo.file_id

    if file_id not in _file_path_cache:
        tg_file = await bot.get_file(file_id)
        _file_path_cache[file_id] = tg_file.file_path

    file_path = _file_path_cache[file_id]
    url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"

    async with aiohttp.ClientSession() as http_session:
        async with http_session.get(url) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=502, detail="Download error")
            content = await resp.read()

    return Response(content=content, media_type="image/jpeg")


# ==========================
# Корзина
# ==========================

@router.get("/my-offers")
async def get_my_offers(user: dict = Depends(get_current_user)):
    offers = await OfferService.get_user_offers(user["shop_id"], user["id"])
    return offers


@router.get("/cart")
async def get_cart(user: dict = Depends(get_current_user)):
    items = await CartService.get_items(user["shop_id"], user["id"])
    total = sum(item["subtotal"] for item in items)
    return {"items": items, "total": total}


@router.post("/cart/add")
async def add_to_cart(req: AddToCartRequest, user: dict = Depends(get_current_user)):
    error = await CartService.add_item(
        user["shop_id"],
        telegram_user_id=user["id"],
        product_id=req.product_id,
        variant_id=req.variant_id,
        quantity=req.quantity,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {"ok": True}


@router.post("/cart/inc/{cart_item_id}")
async def inc_cart_item(cart_item_id: int, user: dict = Depends(get_current_user)):
    await CartService.change_quantity(user["shop_id"], user["id"], cart_item_id, +1)
    return {"ok": True}


@router.post("/cart/dec/{cart_item_id}")
async def dec_cart_item(cart_item_id: int, user: dict = Depends(get_current_user)):
    await CartService.change_quantity(user["shop_id"], user["id"], cart_item_id, -1)
    return {"ok": True}


@router.delete("/cart/{cart_item_id}")
async def remove_cart_item(cart_item_id: int, user: dict = Depends(get_current_user)):
    await CartService.remove_item(user["shop_id"], user["id"], cart_item_id)
    return {"ok": True}


# ==========================
# Промокоды
# ==========================

@router.post("/promo/validate")
async def validate_promo(req: ValidatePromoRequest, user: dict = Depends(get_current_user)):
    cart = await CartService.get_items(user["shop_id"], user["id"])
    cart_total = sum(item["subtotal"] for item in cart)

    if cart_total == 0:
        raise HTTPException(status_code=400, detail="Корзина пуста")

    result = await PromoCodeService.validate(user["shop_id"], req.code, cart_total)

    if result is None:
        raise HTTPException(status_code=404, detail="Промокод недействителен")

    return result


# ==========================
# Заказы
# ==========================

@router.get("/payment-methods")
async def get_payment_methods():
    """Возвращает доступные способы оплаты."""
    methods = []
    if settings.yookassa_enabled:
        methods.append({
            "id": "yookassa",
            "label": "💳 Картой / СБП",
            "description": "Оплата онлайн через ЮKassa",
        })
    methods.append({
        "id": "manual",
        "label": "🏦 Переводом на карту",
        "description": "Ручная оплата — перевод на карту продавца",
    })
    return methods


@router.get("/orders")
async def list_orders(user: dict = Depends(get_current_user)):
    orders = await OrderService.get_user_orders(user["shop_id"], user["id"], limit=20)
    return orders


@router.post("/orders")
async def create_order(req: CreateOrderRequest, user: dict = Depends(get_current_user)):
    order = await OrderService.create_order(
        user["shop_id"],
        telegram_user_id=user["id"],
        full_name=req.full_name,
        phone=req.phone,
        address="",
        comment=req.comment,
        promo_code=req.promo_code,
        payment_method=req.payment_method,
    )

    if order is None:
        raise HTTPException(status_code=400, detail="Cart is empty")

    if req.payment_method == "yookassa" and settings.yookassa_enabled:
        payment = await OrderPaymentService.create_payment(
            user["shop_id"], order["order_id"]
        )

        if payment is None:
            return {
                "order_id": order["order_id"],
                "total": order["total"],
                "discount": order["discount"],
                "payment": "manual",
                "payment_error": True,
                "card_number": settings.payment_card_number,
                "recipient": settings.payment_recipient_name,
            }

        return {
            "order_id": order["order_id"],
            "total": order["total"],
            "discount": order["discount"],
            "payment": "yookassa",
            "confirmation_url": payment["confirmation_url"],
        }

    return {
        "order_id": order["order_id"],
        "total": order["total"],
        "discount": order["discount"],
        "payment": "manual",
        "card_number": settings.payment_card_number,
        "recipient": settings.payment_recipient_name,
    }


@router.get("/orders/{order_id}")
async def get_order_detail(order_id: int, user: dict = Depends(get_current_user)):
    order = await OrderService.get_user_order(user["shop_id"], user["id"], order_id)

    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    return order
