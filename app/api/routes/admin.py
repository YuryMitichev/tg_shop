from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from aiogram.types import BufferedInputFile
from datetime import datetime

from app.api.admin_auth import require_admin, require_admin_full_access, require_active_subscription
from app.api.rate_limit import limiter
from app.bot.bot import get_bot
from app.core.config import settings as app_settings
from app.database.db import async_session
from app.models.product import Product
from app.services.admin_auth_service import AdminAuthService
from app.services.catalog_admin_service import CatalogAdminService
from app.services.catalog_import_service import CatalogImportService
from app.services.order_admin_service import OrderAdminService
from app.services.review_admin_service import ReviewAdminService
from app.services.stats_service import StatsService
from app.services.admin_user_service import AdminUserService
from app.services.catalog_service import CatalogService
from app.services.message_service import MessageService, DEFAULT_MESSAGES, MESSAGE_LABELS
from app.services.promo_service import PromoCodeService
from app.services.review_service import ReviewService
from app.services.crm_service import CrmService
from app.services.broadcast_service import BroadcastService
from app.services.shop_service import ShopService
from app.models.shop import AVAILABLE_COURIERS, AVAILABLE_PRODUCT_ATTRS
from app.utils.order_status import STATUS_LABELS

router = APIRouter()


# ==========================
# Pydantic схемы
# ==========================

class RequestLoginBody(BaseModel):
    telegram_user_id: int


class VerifyTokenBody(BaseModel):
    token: str


class CreateCategoryBody(BaseModel):
    name: str
    emoji: str | None = None


class UpdateCategoryBody(BaseModel):
    name: str | None = None
    emoji: str | None = None


class VariantCreate(BaseModel):
    volume: str
    price: int
    burn: str | None = None
    stock: int = 0
    size: str | None = None
    color: str | None = None
    scent: str | None = None
    dimensions: str | None = None


class CreateProductBody(BaseModel):
    category_id: int
    name: str
    description: str
    variants: list[VariantCreate]


class UpdateProductBody(BaseModel):
    name: str | None = None
    description: str | None = None
    category_id: int | None = None
    is_active: bool | None = None


class UpdateVariantStockBody(BaseModel):
    stock: int


class UpdateOrderStatusBody(BaseModel):
    status: str


class CreatePromoBody(BaseModel):
    code: str
    discount_type: str
    discount_value: int
    max_uses: int | None = None


class UpdateMessageBody(BaseModel):
    content: str


class UpdateDeliveryBody(BaseModel):
    delivery_enabled: bool
    courier_services: list[str]


class UpdateProductAttrsBody(BaseModel):
    product_attrs: list[str]


class UpdateCompanyInfoBody(BaseModel):
    company_name: str | None = None
    company_inn: str | None = None
    company_address: str | None = None


class UpdatePaymentSettingsBody(BaseModel):
    payment_card_number: str | None = None
    payment_recipient_name: str | None = None
    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None
    yookassa_enabled: bool | None = None
    manual_payment_enabled: bool | None = None


class CreateAdminBody(BaseModel):
    telegram_user_id: int
    display_name: str | None = None


class UpdateNotesBody(BaseModel):
    notes: str


class AddTagBody(BaseModel):
    tag: str


class SendMessageBody(BaseModel):
    text: str


class UpdatePhoneBody(BaseModel):
    phone: str | None = None


class CreateBroadcastBody(BaseModel):
    product_id: int
    discount_percent: int = 0
    variant_id: int | None = None
    filter_tags: list[str] | None = None
    message_text: str | None = None
    expires_at: str | None = None


class PreviewRecipientsBody(BaseModel):
    tags: list[str] | None = None


# ==========================
# Auth
# ==========================

@router.post("/auth/request-login")
@limiter.limit("5/5minutes")
async def request_login(request: Request, body: RequestLoginBody):
    ok = await AdminAuthService.request_login(body.telegram_user_id)

    if not ok:
        return {"ok": False, "error": "Пользователь не является администратором"}

    return {"ok": True}


@router.post("/auth/verify-token")
@limiter.limit("20/minute")
async def verify_login_token(request: Request, body: VerifyTokenBody):
    token = await AdminAuthService.verify_login_token(body.token)

    if token is None:
        return {"ok": False, "error": "Неверная или истекшая ссылка"}

    response = JSONResponse(content={"ok": True})
    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        secure=not app_settings.debug,
        samesite="lax",
        domain=app_settings.cookie_domain,
        path="/",
        max_age=86400,
    )
    return response


@router.post("/auth/logout")
async def logout():
    response = JSONResponse(content={"ok": True})
    response.delete_cookie(
        key="admin_token",
        domain=app_settings.cookie_domain,
        path="/",
    )
    return response


@router.get("/auth/me")
async def get_me(admin: dict = Depends(require_admin_full_access)):
    shop = await ShopService.get(admin["shop_id"])
    return {
        "telegram_user_id": admin["admin_id"],
        "shop_id": admin["shop_id"],
        "shop_name": shop["name"] if shop else None,
        "subscription_active": admin.get("subscription_active", True),
        "is_super_admin": admin.get("is_super_admin", False),
    }


# ==========================
# Dashboard / Статистика
# ==========================

@router.get("/stats")
async def get_stats(admin: dict = Depends(require_active_subscription)):
    return await StatsService.get_stats(admin["shop_id"])


@router.get("/analytics/revenue")
async def get_revenue_chart(days: int = 30, admin: dict = Depends(require_active_subscription)):
    return await StatsService.get_revenue_chart(admin["shop_id"], days)


@router.get("/analytics/overview")
async def get_analytics_overview(days: int = 30, admin: dict = Depends(require_active_subscription)):
    return await StatsService.get_analytics_overview(admin["shop_id"], days)


@router.get("/analytics/categories")
async def get_category_breakdown(days: int = 30, admin: dict = Depends(require_active_subscription)):
    return await StatsService.get_category_breakdown(admin["shop_id"], days)


@router.get("/analytics/products")
async def get_product_stats(days: int = 30, admin: dict = Depends(require_active_subscription)):
    return await StatsService.get_product_stats(admin["shop_id"], days)


@router.get("/analytics/customers")
async def get_customer_stats(days: int = 30, admin: dict = Depends(require_active_subscription)):
    return await StatsService.get_customer_stats(admin["shop_id"], days)


@router.get("/analytics/promos")
async def get_promo_stats(days: int = 30, admin: dict = Depends(require_active_subscription)):
    return await StatsService.get_promo_stats(admin["shop_id"], days)


@router.get("/analytics/reviews")
async def get_review_stats(admin: dict = Depends(require_active_subscription)):
    return await StatsService.get_review_stats(admin["shop_id"])


# ==========================
# Категории
# ==========================

@router.get("/categories")
async def list_categories(admin: dict = Depends(require_admin)):
    return await CatalogAdminService.get_categories(admin["shop_id"])


@router.post("/categories")
async def create_category(body: CreateCategoryBody, admin: dict = Depends(require_active_subscription)):
    category_id = await CatalogAdminService.create_category(admin["shop_id"], body.name, body.emoji)
    return {"id": category_id}


@router.put("/categories/{category_id}")
async def update_category(category_id: int, body: UpdateCategoryBody, admin: dict = Depends(require_active_subscription)):
    if body.name is not None:
        await CatalogAdminService.rename_category(admin["shop_id"], category_id, body.name)
    if body.emoji is not None:
        await CatalogAdminService.update_category_emoji(admin["shop_id"], category_id, body.emoji)
    return {"ok": True}


@router.delete("/categories/{category_id}")
async def delete_category(category_id: int, admin: dict = Depends(require_active_subscription)):
    ok = await CatalogAdminService.delete_category(admin["shop_id"], category_id)

    if not ok:
        return {"ok": False, "error": "В категории есть товары"}

    return {"ok": True}


# ==========================
# Товары
# ==========================

@router.get("/products")
async def list_products(category_id: int | None = None, admin: dict = Depends(require_active_subscription)):
    if category_id is not None:
        return await CatalogAdminService.get_products(admin["shop_id"], category_id)
    return await CatalogAdminService.get_all_products(admin["shop_id"])


@router.get("/products/{product_id}")
async def get_product(product_id: int, admin: dict = Depends(require_active_subscription)):
    product = await CatalogAdminService.get_product(admin["shop_id"], product_id)

    if product is None:
        return {"ok": False, "error": "Не найден"}

    return product


@router.post("/products")
async def create_product(body: CreateProductBody, admin: dict = Depends(require_active_subscription)):
    product_id = await CatalogAdminService.create_product(
        admin["shop_id"],
        category_id=body.category_id,
        name=body.name,
        description=body.description,
        variants=[v.model_dump() for v in body.variants],
    )
    return {"id": product_id}


@router.put("/products/{product_id}")
async def update_product(product_id: int, body: UpdateProductBody, admin: dict = Depends(require_active_subscription)):
    await CatalogAdminService.update_product(
        admin["shop_id"],
        product_id,
        name=body.name,
        description=body.description,
    )

    if body.category_id is not None:
        async with async_session() as session:
            product = await session.get(Product, product_id)
            if product and product.shop_id == admin["shop_id"]:
                product.category_id = body.category_id
                await session.commit()

    if body.is_active is not None:
        await CatalogAdminService.toggle_active(admin["shop_id"], product_id)

    return {"ok": True}


@router.delete("/products/{product_id}")
async def delete_product(product_id: int, admin: dict = Depends(require_active_subscription)):
    await CatalogAdminService.delete_product(admin["shop_id"], product_id)
    return {"ok": True}


@router.patch("/products/{product_id}/toggle")
async def toggle_product(product_id: int, admin: dict = Depends(require_active_subscription)):
    is_active = await CatalogAdminService.toggle_active(admin["shop_id"], product_id)
    return {"is_active": is_active}


@router.post("/products/{product_id}/photos")
async def upload_photo(
    product_id: int,
    file: UploadFile = File(...),
    admin: dict = Depends(require_active_subscription),
):
    content = await file.read()

    bot = get_bot(admin["shop_id"])
    if bot is None:
        return {"ok": False, "error": "Бот недоступен"}

    input_file = BufferedInputFile(content, file.filename or "photo.jpg")
    msg = await bot.send_photo(admin["admin_id"], input_file)

    file_id = msg.photo[-1].file_id

    await bot.delete_message(admin["admin_id"], msg.message_id)

    photo_id = await CatalogAdminService.add_photo(admin["shop_id"], product_id, file_id)

    return {"id": photo_id, "file_id": file_id}


@router.delete("/products/{product_id}/photos/{photo_id}")
async def delete_photo(product_id: int, photo_id: int, admin: dict = Depends(require_active_subscription)):
    await CatalogAdminService.delete_photo(admin["shop_id"], photo_id)
    return {"ok": True}


@router.patch("/variants/{variant_id}/stock")
async def update_variant_stock(
    variant_id: int,
    body: UpdateVariantStockBody,
    admin: dict = Depends(require_active_subscription),
):
    ok = await CatalogAdminService.update_variant_stock(admin["shop_id"], variant_id, body.stock)
    if not ok:
        return {"ok": False, "error": "Вариант не найден"}
    return {"ok": True}


# ==========================
# Импорт каталога (Ozon / WB / ЯМ)
# ==========================

MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024  # 10 МБ
IMPORT_CHUNK_SIZE = 64 * 1024  # 64 КБ


async def _read_upload_with_limit(
    file: UploadFile,
    max_size: int = MAX_IMPORT_FILE_SIZE,
    chunk_size: int = IMPORT_CHUNK_SIZE,
) -> bytes:
    """Читает UploadFile чанками, прерываясь при превышении max_size.

    В отличие от file.read(), не загружает весь файл в память:
    если файл превышает лимит, чтение обрывается после max_size + chunk_size.
    """
    buf = bytearray()
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"Файл слишком большой (макс. {max_size // (1024 * 1024)} МБ)",
            )
    return bytes(buf)


class ConfirmImportRow(BaseModel):
    name: str
    price: int = 0
    stock: int = 0


class ConfirmImportBody(BaseModel):
    rows: list[ConfirmImportRow]
    category_id: int | None = None


@router.post("/catalog/import/preview")
async def preview_catalog_import(
    source: str = "ozon",
    file: UploadFile = File(...),
    admin: dict = Depends(require_active_subscription),
):
    if source not in ("ozon", "wb", "ym"):
        raise HTTPException(status_code=400, detail="source должен быть ozon, wb или ym")

    file_bytes = await _read_upload_with_limit(file, MAX_IMPORT_FILE_SIZE)

    preview = CatalogImportService.parse_marketplace_file(file_bytes, source)
    return preview


@router.post("/catalog/import/confirm")
async def confirm_catalog_import(
    body: ConfirmImportBody,
    admin: dict = Depends(require_active_subscription),
):
    if not body.rows:
        raise HTTPException(status_code=400, detail="Список строк пуст")

    result = await CatalogImportService.import_rows(
        shop_id=admin["shop_id"],
        rows=[r.model_dump() for r in body.rows],
        category_id=body.category_id,
    )
    return result


# ==========================
# Заказы
# ==========================

@router.get("/orders")
async def list_orders(
    status: str | None = None,
    page: int = 1,
    per_page: int = 20,
    admin: dict = Depends(require_admin),
):
    return await OrderAdminService.get_orders_filtered(admin["shop_id"], status, page, per_page)


@router.get("/orders/{order_id}")
async def get_order_detail(order_id: int, admin: dict = Depends(require_admin)):
    order = await OrderAdminService.get_order_detail(admin["shop_id"], order_id)

    if order is None:
        return {"ok": False, "error": "Не найден"}

    return order


@router.patch("/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    body: UpdateOrderStatusBody,
    admin: dict = Depends(require_admin),
):
    await OrderAdminService.set_order_status(admin["shop_id"], order_id, body.status)
    return {"ok": True}


@router.get("/statuses")
async def get_statuses(admin: dict = Depends(require_admin)):
    return [{"value": k, "label": v} for k, v in STATUS_LABELS.items()]


# ==========================
# Пользователи
# ==========================

@router.get("/users")
async def list_users(admin: dict = Depends(require_active_subscription)):
    return await OrderAdminService.get_users(admin["shop_id"])


# ==========================
# Промокоды
# ==========================

@router.get("/promos")
async def list_promos(admin: dict = Depends(require_active_subscription)):
    return await PromoCodeService.get_all(admin["shop_id"])


@router.post("/promos")
async def create_promo(body: CreatePromoBody, admin: dict = Depends(require_active_subscription)):
    promo_id = await PromoCodeService.create(
        admin["shop_id"],
        code=body.code,
        discount_type=body.discount_type,
        discount_value=body.discount_value,
        max_uses=body.max_uses,
    )
    return {"id": promo_id}


@router.patch("/promos/{promo_id}/toggle")
async def toggle_promo(promo_id: int, admin: dict = Depends(require_active_subscription)):
    await PromoCodeService.toggle_active(admin["shop_id"], promo_id)
    return {"ok": True}


@router.delete("/promos/{promo_id}")
async def delete_promo(promo_id: int, admin: dict = Depends(require_active_subscription)):
    await PromoCodeService.delete(admin["shop_id"], promo_id)
    return {"ok": True}


# ==========================
# Отзывы
# ==========================

@router.get("/reviews")
async def list_reviews(admin: dict = Depends(require_active_subscription)):
    return await ReviewAdminService.get_all_reviews(admin["shop_id"])


@router.delete("/reviews/{review_id}")
async def delete_review(review_id: int, admin: dict = Depends(require_active_subscription)):
    ok = await ReviewAdminService.delete_review(admin["shop_id"], review_id)
    return {"ok": ok}


# ==========================
# Настройки (сообщения)
# ==========================

@router.get("/settings/messages")
async def list_messages(admin: dict = Depends(require_active_subscription)):
    return await MessageService.get_all(admin["shop_id"])


@router.get("/settings/messages/{key}")
async def get_message(key: str, admin: dict = Depends(require_active_subscription)):
    msg = await MessageService.get_one(admin["shop_id"], key)

    if msg is None:
        return {"ok": False, "error": "Не найдено"}

    return msg


@router.put("/settings/messages/{key}")
async def update_message(key: str, body: UpdateMessageBody, admin: dict = Depends(require_active_subscription)):
    await MessageService.update(admin["shop_id"], key, body.content)
    return {"ok": True}


@router.post("/settings/messages/{key}/reset")
async def reset_message(key: str, admin: dict = Depends(require_active_subscription)):
    await MessageService.reset(admin["shop_id"], key)
    return {"ok": True}


@router.get("/settings/payment")
async def get_payment_settings(admin: dict = Depends(require_active_subscription)):
    return {
        "payment_card_number": app_settings.payment_card_number,
        "payment_recipient_name": app_settings.payment_recipient_name,
        "tinkoff_enabled": app_settings.tinkoff_enabled,
    }


# ==========================
# Настройки (доставка)
# ==========================

@router.get("/settings/delivery")
async def get_delivery_settings(admin: dict = Depends(require_active_subscription)):
    shop = await ShopService.get(admin["shop_id"])
    return {
        "delivery_enabled": shop["delivery_enabled"] if shop else True,
        "courier_services": shop["courier_services"] if shop else [],
        "available_couriers": AVAILABLE_COURIERS,
    }


@router.put("/settings/delivery")
async def update_delivery_settings(body: UpdateDeliveryBody, admin: dict = Depends(require_active_subscription)):
    await ShopService.update_delivery_settings(
        admin["shop_id"],
        body.delivery_enabled,
        body.courier_services,
    )
    return {"ok": True}


# ==========================
# Настройки (характеристики товара)
# ==========================

@router.get("/settings/product-attrs")
async def get_product_attrs(admin: dict = Depends(require_active_subscription)):
    shop = await ShopService.get(admin["shop_id"])
    return {
        "product_attrs": shop["product_attrs"] if shop else ["volume"],
        "available": AVAILABLE_PRODUCT_ATTRS,
    }


@router.put("/settings/product-attrs")
async def update_product_attrs(body: UpdateProductAttrsBody, admin: dict = Depends(require_active_subscription)):
    await ShopService.update_product_attrs(admin["shop_id"], body.product_attrs)
    return {"ok": True}


# ==========================
# Настройки (реквизиты)
# ==========================

@router.get("/settings/company")
async def get_company_info(admin: dict = Depends(require_active_subscription)):
    shop = await ShopService.get(admin["shop_id"])
    return {
        "company_name": shop["company_name"] if shop else None,
        "company_inn": shop["company_inn"] if shop else None,
        "company_address": shop["company_address"] if shop else None,
    }


@router.put("/settings/company")
async def update_company_info(body: UpdateCompanyInfoBody, admin: dict = Depends(require_active_subscription)):
    await ShopService.update_company_info(
        admin["shop_id"],
        body.company_name,
        body.company_inn,
        body.company_address,
    )
    return {"ok": True}


# ==========================
# Настройки (платежи магазина)
# ==========================

@router.get("/settings/payments")
async def get_shop_payment_settings(admin: dict = Depends(require_active_subscription)):
    shop = await ShopService.get(admin["shop_id"])
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    return {
        "payment_card_number": shop["payment_card_number"],
        "payment_recipient_name": shop["payment_recipient_name"],
        "yookassa_shop_id": shop["yookassa_shop_id"],
        "yookassa_secret_key_masked": shop["yookassa_secret_key_masked"],
        "yookassa_enabled": shop["yookassa_enabled"],
        "manual_payment_enabled": shop["manual_payment_enabled"],
    }


@router.put("/settings/payments")
async def update_shop_payment_settings(
    body: UpdatePaymentSettingsBody,
    admin: dict = Depends(require_active_subscription),
):
    result = await ShopService.update_payment_settings(
        admin["shop_id"],
        payment_card_number=body.payment_card_number,
        payment_recipient_name=body.payment_recipient_name,
        yookassa_shop_id=body.yookassa_shop_id,
        yookassa_secret_key=body.yookassa_secret_key,
        yookassa_enabled=body.yookassa_enabled,
        manual_payment_enabled=body.manual_payment_enabled,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    return {"ok": True}


# ==========================
# Администраторы
# ==========================

@router.get("/admins")
async def list_admins(admin: dict = Depends(require_active_subscription)):
    return await AdminUserService.get_all(admin["shop_id"])


@router.post("/admins")
async def create_admin(body: CreateAdminBody, admin: dict = Depends(require_active_subscription)):
    admin_id = await AdminUserService.add(admin["shop_id"], body.telegram_user_id, body.display_name)
    return {"id": admin_id}


@router.delete("/admins/{admin_id}")
async def delete_admin(admin_id: int, admin: dict = Depends(require_active_subscription)):
    if admin_id < 0:
        return {"ok": False, "error": "Нельзя удалить супер-админа из .env"}
    ok = await AdminUserService.delete(admin["shop_id"], admin_id)
    return {"ok": ok}


# ==========================
# CRM — Пользователи
# ==========================

@router.get("/crm/users")
async def crm_list_users(
    search: str | None = None,
    tag: str | None = None,
    page: int = 1,
    per_page: int = 20,
    admin: dict = Depends(require_admin),
):
    return await CrmService.get_users(admin["shop_id"], search, tag, page, per_page)


@router.get("/crm/users/{telegram_user_id}")
async def crm_user_detail(telegram_user_id: int, admin: dict = Depends(require_admin)):
    detail = await CrmService.get_user_detail(admin["shop_id"], telegram_user_id)
    if detail is None:
        return {"ok": False, "error": "Пользователь не найден"}
    return detail


@router.put("/crm/users/{telegram_user_id}/notes")
async def crm_update_notes(
    telegram_user_id: int,
    body: UpdateNotesBody,
    admin: dict = Depends(require_active_subscription),
):
    ok = await CrmService.update_notes(admin["shop_id"], telegram_user_id, body.notes)
    return {"ok": ok}


@router.put("/crm/users/{telegram_user_id}/phone")
async def crm_update_phone(
    telegram_user_id: int,
    body: UpdatePhoneBody,
    admin: dict = Depends(require_active_subscription),
):
    ok = await CrmService.update_phone(admin["shop_id"], telegram_user_id, body.phone)
    return {"ok": ok}


@router.post("/crm/users/{telegram_user_id}/tags")
async def crm_add_tag(
    telegram_user_id: int,
    body: AddTagBody,
    admin: dict = Depends(require_active_subscription),
):
    ok = await CrmService.add_tag(admin["shop_id"], telegram_user_id, body.tag)
    return {"ok": ok}


@router.delete("/crm/users/{telegram_user_id}/tags/{tag}")
async def crm_remove_tag(
    telegram_user_id: int,
    tag: str,
    admin: dict = Depends(require_active_subscription),
):
    ok = await CrmService.remove_tag(admin["shop_id"], telegram_user_id, tag)
    return {"ok": ok}


@router.get("/crm/tags")
async def crm_all_tags(admin: dict = Depends(require_active_subscription)):
    return await CrmService.get_all_tags(admin["shop_id"])


# ==========================
# CRM — История коммуникации
# ==========================

@router.get("/crm/users/{telegram_user_id}/messages")
async def crm_messages(
    telegram_user_id: int,
    page: int = 1,
    per_page: int = 50,
    admin: dict = Depends(require_active_subscription),
):
    return await CrmService.get_communication_history(admin["shop_id"], telegram_user_id, page, per_page)


@router.post("/crm/users/{telegram_user_id}/send")
async def crm_send_message(
    telegram_user_id: int,
    body: SendMessageBody,
    admin: dict = Depends(require_active_subscription),
):
    bot = get_bot(admin["shop_id"])
    if bot is None:
        return {"ok": False, "error": "Бот недоступен"}

    text = body.text.strip()
    if not text:
        return {"ok": False, "error": "Пустое сообщение"}

    try:
        await bot.send_message(telegram_user_id, text)
    except Exception:
        return {"ok": False, "error": "Не удалось отправить. Возможно, пользователь заблокировал бота."}

    await CrmService.log_message(
        shop_id=admin["shop_id"],
        telegram_user_id=telegram_user_id,
        direction="out",
        message_type="text",
        text=text,
        admin_id=admin["admin_id"],
    )
    return {"ok": True}


# ==========================
# Рассылки
# ==========================

@router.get("/broadcasts")
async def list_broadcasts(
    page: int = 1,
    per_page: int = 20,
    admin: dict = Depends(require_active_subscription),
):
    return await BroadcastService.get_broadcasts(admin["shop_id"], page, per_page)


@router.get("/broadcasts/{broadcast_id}")
async def get_broadcast(broadcast_id: int, admin: dict = Depends(require_active_subscription)):
    broadcast = await BroadcastService.get_broadcast(admin["shop_id"], broadcast_id)
    if broadcast is None:
        return {"ok": False, "error": "Рассылка не найдена"}
    return broadcast


@router.post("/broadcasts/preview")
async def preview_recipients(
    body: PreviewRecipientsBody,
    admin: dict = Depends(require_active_subscription),
):
    return await BroadcastService.preview_recipients(admin["shop_id"], body.tags)


@router.post("/broadcasts")
async def create_broadcast(
    body: CreateBroadcastBody,
    admin: dict = Depends(require_active_subscription),
):
    try:
        expires_dt = None
        if body.expires_at:
            expires_dt = datetime.fromisoformat(body.expires_at)

        broadcast = await BroadcastService.create_broadcast(
            admin["shop_id"],
            product_id=body.product_id,
            discount_percent=body.discount_percent,
            filter_tags=body.filter_tags,
            variant_id=body.variant_id,
            message_text=body.message_text,
            created_by=admin["admin_id"],
            expires_at=expires_dt,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "broadcast_id": broadcast.id}


@router.post("/broadcasts/{broadcast_id}/send")
@limiter.limit("3/minute")
async def send_broadcast(
    request: Request,
    broadcast_id: int,
    admin: dict = Depends(require_active_subscription),
):
    bot = get_bot(admin["shop_id"])
    if bot is None:
        return {"ok": False, "error": "Бот недоступен"}

    result = await BroadcastService.send_broadcast(admin["shop_id"], broadcast_id, bot)
    return result
