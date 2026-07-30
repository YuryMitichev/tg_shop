import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user
from app.bot.bot import get_bot
from app.core.config import settings
from app.database.db import async_session
from app.models.product import Product
from app.models.product_photo import ProductPhoto
from app.services.catalog_service import CatalogService
from app.services.cart_service import CartService
from app.services.order_service import OrderService
from app.services.promo_service import PromoCodeService
from app.services.review_service import ReviewService

router = APIRouter()


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


class ValidatePromoRequest(BaseModel):
    code: str


# ==========================
# Каталог
# ==========================

@router.get("/categories")
async def list_categories():
    categories = await CatalogService.get_categories()
    return categories


@router.get("/products")
async def list_products(category_id: int = Query(...)):
    products = await CatalogService.get_products(category_id)

    result = []
    for p in products:
        prices = [v["price"] for v in p["variants"]]
        summary = await ReviewService.get_rating_summary(p["id"])

        result.append({
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "price_from": min(prices) if prices else 0,
            "price_to": max(prices) if prices else 0,
            "photo_id": p["photos"][0]["id"] if p.get("photos") else None,
            "rating": summary,
        })

    return result


@router.get("/products/{product_id}")
async def get_product_detail(product_id: int):
    product = await CatalogService.get_product(product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    summary = await ReviewService.get_rating_summary(product_id)
    reviews = await ReviewService.get_product_reviews(product_id, limit=10)

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

    bot = get_bot()
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

@router.get("/cart")
async def get_cart(user: dict = Depends(get_current_user)):
    items = await CartService.get_items(user["id"])
    total = sum(item["subtotal"] for item in items)
    return {"items": items, "total": total}


@router.post("/cart/add")
async def add_to_cart(req: AddToCartRequest, user: dict = Depends(get_current_user)):
    await CartService.add_item(
        telegram_user_id=user["id"],
        product_id=req.product_id,
        variant_id=req.variant_id,
        quantity=req.quantity,
    )
    return {"ok": True}


@router.post("/cart/inc/{cart_item_id}")
async def inc_cart_item(cart_item_id: int, user: dict = Depends(get_current_user)):
    await CartService.change_quantity(user["id"], cart_item_id, +1)
    return {"ok": True}


@router.post("/cart/dec/{cart_item_id}")
async def dec_cart_item(cart_item_id: int, user: dict = Depends(get_current_user)):
    await CartService.change_quantity(user["id"], cart_item_id, -1)
    return {"ok": True}


@router.delete("/cart/{cart_item_id}")
async def remove_cart_item(cart_item_id: int, user: dict = Depends(get_current_user)):
    await CartService.remove_item(user["id"], cart_item_id)
    return {"ok": True}


# ==========================
# Промокоды
# ==========================

@router.post("/promo/validate")
async def validate_promo(req: ValidatePromoRequest, user: dict = Depends(get_current_user)):
    cart = await CartService.get_items(user["id"])
    cart_total = sum(item["subtotal"] for item in cart)

    if cart_total == 0:
        raise HTTPException(status_code=400, detail="Корзина пуста")

    result = await PromoCodeService.validate(req.code, cart_total)

    if result is None:
        raise HTTPException(status_code=404, detail="Промокод недействителен")

    return result


# ==========================
# Заказы
# ==========================

@router.get("/orders")
async def list_orders(user: dict = Depends(get_current_user)):
    orders = await OrderService.get_user_orders(user["id"], limit=20)
    return orders


@router.post("/orders")
async def create_order(req: CreateOrderRequest, user: dict = Depends(get_current_user)):
    order = await OrderService.create_order(
        telegram_user_id=user["id"],
        full_name=req.full_name,
        phone=req.phone,
        address="",
        comment=req.comment,
        promo_code=req.promo_code,
    )

    if order is None:
        raise HTTPException(status_code=400, detail="Cart is empty")

    if settings.tinkoff_enabled:
        return {
            "order_id": order["order_id"],
            "total": order["total"],
            "discount": order["discount"],
            "payment": "qr",
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
    order = await OrderService.get_user_order(user["id"], order_id)

    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    return order
