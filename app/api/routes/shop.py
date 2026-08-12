import aiohttp
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user, get_optional_user
from app.api.rate_limit import limiter, user_or_ip_key
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
from app.services.legal_document_service import LegalDocumentService, LEGAL_DOCUMENT_TITLES
from app.services.product_attr_service import ProductAttrService

router = APIRouter()


async def get_shop_id(x_shop_id: int | None = Header(None, alias="X-Shop-Id")) -> int:
    if x_shop_id is None:
        raise HTTPException(status_code=400, detail="X-Shop-Id header is required")
    return x_shop_id


@router.get("/shop-config")
async def get_shop_config(shop_id: int = Depends(get_shop_id)):
    """Конфиг магазина для мини-аппа: включённые характеристики товара и т.д."""
    shop = await ShopService.get(shop_id)

    attr_defs = await ProductAttrService.list_defs(shop_id) if shop else []

    product_attrs = ["volume"] + [d["key"] for d in attr_defs]
    attr_labels = {"volume": "Объём"}
    for d in attr_defs:
        attr_labels[d["key"]] = d["label"]

    bot_username = None
    bot = get_bot(shop_id)
    if bot:
        try:
            me = await bot.get_me()
            bot_username = me.username
        except Exception:
            pass

    return {
        "product_attrs": product_attrs,
        "attr_labels": attr_labels,
        "bot_username": bot_username,
        "company": {
            "name": shop["company_name"] if shop else None,
            "inn": shop["company_inn"] if shop else None,
            "address": shop["company_address"] if shop else None,
        } if shop else None,
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


class CreateReviewRequest(BaseModel):
    product_id: int
    rating: int
    text: str | None = None


class ContactManagerRequest(BaseModel):
    product_id: int
    message: str


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
async def get_payment_methods(shop_id: int = Depends(get_shop_id)):
    """Возвращает доступные способы оплаты для конкретного магазина."""
    shop = await ShopService.get(shop_id)
    methods = []

    if shop and shop["yookassa_enabled"]:
        methods.append({
            "id": "yookassa",
            "label": "💳 Картой / СБП",
            "description": "Оплата онлайн через ЮKassa",
        })

    if shop is None or shop["manual_payment_enabled"]:
        card_number = (shop["payment_card_number"] if shop else None) or settings.payment_card_number
        recipient = (shop["payment_recipient_name"] if shop else None) or settings.payment_recipient_name
        methods.append({
            "id": "manual",
            "label": "🏦 Переводом на карту",
            "description": "Ручная оплата — перевод на карту продавца",
            "card_number": card_number,
            "recipient": recipient,
        })

    return methods


@router.get("/orders")
async def list_orders(user: dict = Depends(get_current_user)):
    orders = await OrderService.get_user_orders(user["shop_id"], user["id"], limit=20)
    return orders


@router.post("/orders")
@limiter.limit("10/minute", key_func=user_or_ip_key)
async def create_order(request: Request, req: CreateOrderRequest, user: dict = Depends(get_current_user)):
    unavailable = await CartService.check_availability(user["shop_id"], user["id"])

    if unavailable:
        raise HTTPException(
            status_code=409,
            detail={"error": "out_of_stock", "items": unavailable},
        )

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

    if order.get("error") == "out_of_stock":
        raise HTTPException(
            status_code=409,
            detail={"error": "out_of_stock", "items": order["items"]},
        )

    shop = await ShopService.get(user["shop_id"])
    shop_yookassa_enabled = shop["yookassa_enabled"] if shop else False
    card_number = (shop["payment_card_number"] if shop else None) or settings.payment_card_number
    recipient = (shop["payment_recipient_name"] if shop else None) or settings.payment_recipient_name

    if req.payment_method == "yookassa" and shop_yookassa_enabled:
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
                "card_number": card_number,
                "recipient": recipient,
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
        "card_number": card_number,
        "recipient": recipient,
    }


@router.get("/orders/{order_id}")
async def get_order_detail(order_id: int, user: dict = Depends(get_current_user)):
    order = await OrderService.get_user_order(user["shop_id"], user["id"], order_id)

    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    return order


# ==========================
# Отзывы и связь с менеджером
# ==========================

@router.post("/reviews")
async def create_review(req: CreateReviewRequest, user: dict = Depends(get_current_user)):
    if not (1 <= req.rating <= 5):
        raise HTTPException(status_code=400, detail="Оценка должна быть от 1 до 5")

    if not await OrderService.has_purchased(user["shop_id"], user["id"], req.product_id):
        raise HTTPException(status_code=403, detail="Отзывать могут только покупатели этого товара")

    await ReviewService.create_or_update(
        user["shop_id"],
        req.product_id,
        user["id"],
        req.rating,
        req.text,
    )
    return {"ok": True}


@router.post("/contact-manager")
async def contact_manager(req: ContactManagerRequest, user: dict = Depends(get_current_user)):
    shop = await ShopService.get(user["shop_id"])
    if shop is None:
        raise HTTPException(status_code=404, detail="Магазин не найден")

    owner_id = shop.get("owner_telegram_id")
    if not owner_id:
        raise HTTPException(status_code=503, detail="Не указан получатель сообщения")

    product = await CatalogService.get_product(user["shop_id"], req.product_id)
    product_name = product["name"] if product else f"#{req.product_id}"

    bot = get_bot(user["shop_id"])
    if bot is None:
        raise HTTPException(status_code=503, detail="Бот недоступен")

    username = user.get("username")
    user_line = f"@{username}" if username else f"id: {user['id']}"

    text = (
        f"📩 Сообщение от покупателя\n\n"
        f"Товар: {product_name}\n"
        f"Пользователь: {user.get('first_name') or ''} ({user_line})\n\n"
        f"{req.message}"
    )
    try:
        await bot.send_message(owner_id, text)
    except Exception:
        raise HTTPException(status_code=502, detail="Не удалось отправить сообщение")

    return {"ok": True}


@router.get("/legal/{shop_id}/offer")
async def get_public_offer(shop_id: int):
    """Публичная оферта магазина — доступна без авторизации."""
    shop = await ShopService.get(shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="Магазин не найден")
    if shop.get("offer_text"):
        return {"text": shop["offer_text"]}
    doc = await LegalDocumentService.render_document(shop_id, "public_offer")
    return {"text": doc["text"]}


@router.get("/legal/{shop_id}/privacy")
async def get_public_privacy(shop_id: int):
    """Политика конфиденциальности магазина — доступна без авторизации."""
    shop = await ShopService.get(shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="Магазин не найден")
    if shop.get("privacy_policy_text"):
        return {"text": shop["privacy_policy_text"]}
    doc = await LegalDocumentService.render_document(shop_id, "privacy_policy")
    return {"text": doc["text"]}


@router.get("/legal/{shop_id}/documents")
async def list_public_legal_documents(shop_id: int):
    """Список правовых документов магазина — доступен без авторизации."""
    docs = await LegalDocumentService.get_all_documents(shop_id)
    if docs is None:
        raise HTTPException(status_code=404, detail="Магазин не найден")
    return [
        {
            "document_type": d["document_type"],
            "title": d["title"],
        }
        for d in docs
    ]


@router.get("/legal/{shop_id}/documents/{document_type}")
async def get_public_legal_document(shop_id: int, document_type: str):
    """Полный текст правового документа — доступен без авторизации."""
    if document_type not in LEGAL_DOCUMENT_TITLES:
        raise HTTPException(status_code=404, detail="Документ не найден")
    doc = await LegalDocumentService.render_document(shop_id, document_type)
    if doc is None:
        raise HTTPException(status_code=404, detail="Магазин не найден")
    return doc
