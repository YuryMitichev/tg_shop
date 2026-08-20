import asyncio
import logging
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from aiogram.types import BufferedInputFile
from datetime import datetime
from PIL import Image, UnidentifiedImageError

from app.api.admin_auth import (
    require_active_subscription,
    require_admin,
    require_admin_full_access,
    require_catalog_access,
    require_owner,
    require_owner_recent,
    require_support_access,
)
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
from app.services.legal_document_service import LegalDocumentService, LEGAL_DOCUMENT_TITLES
from app.services.product_attr_service import ProductAttrService
from app.models.shop import AVAILABLE_COURIERS
from app.utils.order_status import STATUS_LABELS
from app.utils.validation import normalize_category_emoji

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_PHOTO_FILE_SIZE = 8 * 1024 * 1024
MAX_PHOTO_PIXELS = 25_000_000
PHOTO_UPLOAD_CONCURRENCY = asyncio.Semaphore(2)
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def _validate_image_upload(content: bytes) -> None:
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in ALLOWED_IMAGE_FORMATS:
                raise ValueError("Поддерживаются только JPEG, PNG и WebP")
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_PHOTO_PIXELS:
                raise ValueError("Слишком большое разрешение изображения")
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Файл не является корректным изображением") from exc


# ==========================
# Pydantic схемы
# ==========================

class RequestLoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_user_id: int = Field(gt=0)
    shop_id: int | None = Field(default=None, gt=0)
    panel: Literal["admin", "platform"] = "admin"


class VerifyTokenBody(BaseModel):
    token: str = Field(min_length=32, max_length=128)


class CreateCategoryBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    emoji: str | None = Field(default=None, max_length=16)

    _validate_emoji = field_validator("emoji")(normalize_category_emoji)


class UpdateCategoryBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    emoji: str | None = Field(default=None, max_length=16)

    _validate_emoji = field_validator("emoji")(normalize_category_emoji)


class VariantCreate(BaseModel):
    volume: str = Field(min_length=1, max_length=100)
    price: int = Field(ge=1, le=100_000_000)
    stock: int = Field(default=0, ge=0, le=1_000_000)
    attributes: dict[str, str] = Field(default_factory=dict, max_length=50)


class CreateProductBody(BaseModel):
    category_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=5_000)
    variants: list[VariantCreate] = Field(min_length=1, max_length=100)


class UpdateProductBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5_000)
    category_id: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class UpdateVariantBody(BaseModel):
    volume: str | None = Field(default=None, min_length=1, max_length=100)
    price: int | None = Field(default=None, ge=1, le=100_000_000)
    stock: int | None = Field(default=None, ge=0, le=1_000_000)
    attributes: dict[str, str] | None = Field(default=None, max_length=50)


class UpdateVariantStockBody(BaseModel):
    stock: int = Field(ge=0, le=1_000_000)


class UpdateOrderStatusBody(BaseModel):
    status: Literal["new", "confirmed", "paid", "shipped", "done", "cancelled"]


class CreatePromoBody(BaseModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    discount_type: Literal["percent", "fixed"]
    discount_value: int = Field(gt=0, le=100_000_000)
    max_uses: int | None = Field(default=None, ge=1, le=1_000_000)


class UpdateMessageBody(BaseModel):
    content: str = Field(max_length=4_000)


class UpdateDeliveryBody(BaseModel):
    delivery_enabled: bool
    courier_services: list[str] = Field(max_length=20)


class CreateAttrDefBody(BaseModel):
    label: str = Field(min_length=1, max_length=100)


class UpdateAttrDefBody(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    position: int | None = Field(default=None, ge=0, le=10_000)


class UpdateCompanyInfoBody(BaseModel):
    company_name: str | None = Field(default=None, max_length=200)
    company_inn: str | None = Field(default=None, max_length=20)
    company_address: str | None = Field(default=None, max_length=500)
    legal_type: Literal["individual", "self_employed", "ip", "ooo"] | None = None


class UpdateShopNameBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class UpdatePaymentSettingsBody(BaseModel):
    payment_card_number: str | None = Field(default=None, max_length=32)
    payment_recipient_name: str | None = Field(default=None, max_length=200)
    yookassa_shop_id: str | None = Field(default=None, max_length=64)
    yookassa_secret_key: str | None = Field(default=None, max_length=256)
    yookassa_enabled: bool | None = None
    manual_payment_enabled: bool | None = None


class UpdateLegalDocsBody(BaseModel):
    offer_text: str | None = Field(default=None, max_length=100_000)
    privacy_policy_text: str | None = Field(default=None, max_length=100_000)


class UpdateThemeBody(BaseModel):
    primary_color: str | None = Field(default=None, max_length=7)
    bg_color: str | None = Field(default=None, max_length=7)
    text_color: str | None = Field(default=None, max_length=7)
    button_text_color: str | None = Field(default=None, max_length=7)
    secondary_bg_color: str | None = Field(default=None, max_length=7)
    radius: str | None = Field(default=None, max_length=6)
    font_family: str | None = Field(default=None, max_length=100)
    price_color: str | None = Field(default=None, max_length=7)
    price_size: str | None = Field(default=None, max_length=4)
    price_weight: str | None = Field(default=None, max_length=3)

    @field_validator(
        "primary_color", "bg_color", "text_color", "button_text_color",
        "secondary_bg_color", "price_color",
    )
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value in {None, ""}:
            return value
        if not __import__("re").fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise ValueError("Цвет должен быть в формате #RRGGBB")
        return value

    @field_validator("radius")
    @classmethod
    def validate_radius(cls, value: str | None) -> str | None:
        allowed = {None, "", "0px", "8px", "14px", "20px", "9999px"}
        if value not in allowed:
            raise ValueError("Недопустимое скругление")
        return value

    @field_validator("font_family")
    @classmethod
    def validate_font(cls, value: str | None) -> str | None:
        allowed = {
            None, "", "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "Georgia, 'Times New Roman', serif", "'Courier New', Courier, monospace",
            "'Comic Sans MS', 'Marker Felt', cursive",
        }
        if value not in allowed:
            raise ValueError("Недопустимый шрифт")
        return value

    @field_validator("price_size")
    @classmethod
    def validate_price_size(cls, value: str | None) -> str | None:
        if value not in {None, "", "13px", "14px", "16px", "18px", "22px"}:
            raise ValueError("Недопустимый размер цены")
        return value

    @field_validator("price_weight")
    @classmethod
    def validate_price_weight(cls, value: str | None) -> str | None:
        if value not in {None, "", "400", "500", "600", "700", "800"}:
            raise ValueError("Недопустимая насыщенность цены")
        return value


class UpdateSellerAddendumBody(BaseModel):
    seller_addendum: str | None = Field(default=None, max_length=50_000)


class CreateAdminBody(BaseModel):
    telegram_user_id: int = Field(gt=0)
    display_name: str | None = Field(default=None, max_length=100)
    role: Literal["manager", "content", "support"] = "manager"


class UpdateNotesBody(BaseModel):
    notes: str = Field(max_length=5_000)


class AddTagBody(BaseModel):
    tag: str = Field(min_length=1, max_length=64)


class SendMessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=4_000)


class UpdatePhoneBody(BaseModel):
    phone: str | None = Field(default=None, max_length=30)


class CreateBroadcastBody(BaseModel):
    product_id: int = Field(gt=0)
    discount_percent: int = Field(default=0, ge=0, le=100)
    variant_id: int | None = Field(default=None, gt=0)
    filter_tags: list[str] | None = Field(default=None, max_length=50)
    message_text: str | None = Field(default=None, max_length=3_000)
    expires_at: str | None = Field(default=None, max_length=64)


class PreviewRecipientsBody(BaseModel):
    tags: list[str] | None = Field(default=None, max_length=50)


# ==========================
# Auth
# ==========================

@router.post("/auth/request-login")
@limiter.limit("20/hour")
async def request_login(request: Request, body: RequestLoginBody):
    ok = await AdminAuthService.request_login(
        body.telegram_user_id, shop_id=body.shop_id, panel=body.panel,
    )

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
        secure=True,
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
        "role": admin.get("role", "owner" if admin.get("is_super_admin") else None),
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
async def create_category(body: CreateCategoryBody, admin: dict = Depends(require_catalog_access)):
    category_id = await CatalogAdminService.create_category(admin["shop_id"], body.name, body.emoji)
    return {"id": category_id}


@router.put("/categories/{category_id}")
async def update_category(category_id: int, body: UpdateCategoryBody, admin: dict = Depends(require_catalog_access)):
    if body.name is not None:
        await CatalogAdminService.rename_category(admin["shop_id"], category_id, body.name)
    if body.emoji is not None:
        await CatalogAdminService.update_category_emoji(admin["shop_id"], category_id, body.emoji)
    return {"ok": True}


@router.delete("/categories/{category_id}")
async def delete_category(category_id: int, admin: dict = Depends(require_catalog_access)):
    ok = await CatalogAdminService.delete_category(admin["shop_id"], category_id)

    if not ok:
        return {"ok": False, "error": "В категории есть товары"}

    return {"ok": True}


# ==========================
# Товары
# ==========================

@router.get("/products")
async def list_products(
    category_id: int | None = None,
    page: int = 1,
    per_page: int = 20,
    admin: dict = Depends(require_active_subscription),
):
    if category_id is not None:
        return await CatalogAdminService.get_products(admin["shop_id"], category_id, page, per_page)
    return await CatalogAdminService.get_all_products(admin["shop_id"], page, per_page)


@router.get("/products/{product_id}")
async def get_product(product_id: int, admin: dict = Depends(require_active_subscription)):
    product = await CatalogAdminService.get_product(admin["shop_id"], product_id)

    if product is None:
        return {"ok": False, "error": "Не найден"}

    return product


@router.post("/products")
async def create_product(body: CreateProductBody, admin: dict = Depends(require_catalog_access)):
    product_id = await CatalogAdminService.create_product(
        admin["shop_id"],
        category_id=body.category_id,
        name=body.name,
        description=body.description,
        variants=[v.model_dump() for v in body.variants],
    )
    return {"id": product_id}


@router.put("/products/{product_id}")
async def update_product(product_id: int, body: UpdateProductBody, admin: dict = Depends(require_catalog_access)):
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
        await CatalogAdminService.set_active(admin["shop_id"], product_id, body.is_active)

    return {"ok": True}


@router.delete("/products/{product_id}")
async def delete_product(product_id: int, admin: dict = Depends(require_catalog_access)):
    await CatalogAdminService.delete_product(admin["shop_id"], product_id)
    return {"ok": True}


@router.patch("/products/{product_id}/toggle")
async def toggle_product(product_id: int, admin: dict = Depends(require_catalog_access)):
    is_active = await CatalogAdminService.toggle_active(admin["shop_id"], product_id)
    return {"is_active": is_active}


@router.post("/products/{product_id}/photos")
@limiter.limit("5/minute")
async def upload_photo(
    request: Request,
    product_id: int,
    file: UploadFile = File(...),
    admin: dict = Depends(require_catalog_access),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Поддерживаются только JPEG, PNG и WebP")
    content = await _read_upload_with_limit(file, MAX_PHOTO_FILE_SIZE)
    async with PHOTO_UPLOAD_CONCURRENCY:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_validate_image_upload, content),
                timeout=5,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=408, detail="Проверка изображения заняла слишком много времени") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    bot = get_bot(admin["shop_id"])
    if bot is None:
        return {"ok": False, "error": "Бот недоступен"}

    input_file = BufferedInputFile(content, file.filename or "photo.jpg")
    msg = await bot.send_photo(admin["admin_id"], input_file)

    file_id = msg.photo[-1].file_id

    await bot.delete_message(admin["admin_id"], msg.message_id)

    photo_id = await CatalogAdminService.add_photo(admin["shop_id"], product_id, file_id)

    if photo_id is None:
        raise HTTPException(status_code=404, detail="Товар не найден")

    return {"id": photo_id, "file_id": file_id}


@router.delete("/products/{product_id}/photos/{photo_id}")
async def delete_photo(product_id: int, photo_id: int, admin: dict = Depends(require_catalog_access)):
    await CatalogAdminService.delete_photo(admin["shop_id"], photo_id)
    return {"ok": True}


@router.patch("/variants/{variant_id}/stock")
async def update_variant_stock(
    variant_id: int,
    body: UpdateVariantStockBody,
    admin: dict = Depends(require_catalog_access),
):
    ok = await CatalogAdminService.update_variant_stock(admin["shop_id"], variant_id, body.stock)
    if not ok:
        return {"ok": False, "error": "Вариант не найден"}
    return {"ok": True}


@router.put("/variants/{variant_id}")
async def update_variant(
    variant_id: int,
    body: UpdateVariantBody,
    admin: dict = Depends(require_catalog_access),
):
    ok = await CatalogAdminService.update_variant(
        admin["shop_id"],
        variant_id,
        volume=body.volume,
        price=body.price,
        stock=body.stock,
        attributes=body.attributes,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Вариант не найден")
    return {"ok": True}


@router.post("/products/{product_id}/variants")
async def add_variant(
    product_id: int,
    body: VariantCreate,
    admin: dict = Depends(require_catalog_access),
):
    variant_id = await CatalogAdminService.add_variant(
        admin["shop_id"],
        product_id,
        volume=body.volume,
        price=body.price,
        stock=body.stock,
        attributes=body.attributes,
    )
    if variant_id is None:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return {"id": variant_id}


@router.delete("/variants/{variant_id}")
async def delete_variant(variant_id: int, admin: dict = Depends(require_catalog_access)):
    ok = await CatalogAdminService.delete_variant(admin["shop_id"], variant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Вариант не найден")
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
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5_000)
    category: str = Field(default="", max_length=100)
    price: int = Field(default=0, ge=0, le=100_000_000)


class ConfirmImportBody(BaseModel):
    rows: list[ConfirmImportRow] = Field(max_length=500)
    category_id: int | None = None


@router.post("/catalog/import/preview")
async def preview_catalog_import(
    source: str = "ozon",
    file: UploadFile = File(...),
    admin: dict = Depends(require_catalog_access),
):
    if source not in ("ozon", "wb", "ym"):
        raise HTTPException(status_code=400, detail="source должен быть ozon, wb или ym")

    file_bytes = await _read_upload_with_limit(file, MAX_IMPORT_FILE_SIZE)

    try:
        preview = await asyncio.wait_for(
            asyncio.to_thread(
                CatalogImportService.parse_marketplace_file, file_bytes, source
            ),
            timeout=15,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=408, detail="Обработка XLSX заняла слишком много времени") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return preview


@router.post("/catalog/import/confirm")
async def confirm_catalog_import(
    body: ConfirmImportBody,
    admin: dict = Depends(require_catalog_access),
):
    if not body.rows:
        raise HTTPException(status_code=400, detail="Список строк пуст")

    result = await CatalogImportService.import_rows(
        shop_id=admin["shop_id"],
        rows=[r.model_dump() for r in body.rows],
        category_id=body.category_id,
    )
    result["stock_template_url"] = "/catalog/stock-template"
    return result


# ==========================
# Массовое обновление остатков
# ==========================

@router.get("/catalog/stock-template")
async def download_stock_template(admin: dict = Depends(require_catalog_access)):
    """Скачивает .xlsx-шаблон с остатками всех товаров магазина."""
    data = await CatalogAdminService.get_stock_template_data(admin["shop_id"])
    xlsx_bytes = await asyncio.to_thread(
        CatalogAdminService.generate_stock_template_xlsx, data
    )
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=stock_template.xlsx"},
    )


@router.post("/catalog/stock/bulk-update")
async def bulk_update_stock(
    file: UploadFile = File(...),
    admin: dict = Depends(require_catalog_access),
):
    """Загружает заполненный шаблон остатков и обновляет stock одним batch-запросом."""
    file_bytes = await _read_upload_with_limit(file, MAX_IMPORT_FILE_SIZE)

    try:
        parsed = await asyncio.wait_for(
            asyncio.to_thread(CatalogAdminService.parse_stock_file, file_bytes),
            timeout=15,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=408, detail="Обработка XLSX заняла слишком много времени") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if parsed["errors"]:
        raise HTTPException(status_code=400, detail=(parsed["errors"][:10]))

    result = await CatalogAdminService.apply_stock_updates(
        admin["shop_id"], parsed["updates"]
    )

    logger.info(
        "Bulk stock update: shop_id=%s, updated=%s, not_found=%s",
        admin["shop_id"], result["updated"], result["not_found"],
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
    admin: dict = Depends(require_support_access),
):
    return await OrderAdminService.get_orders_filtered(admin["shop_id"], status, page, per_page)


@router.get("/orders/{order_id}")
async def get_order_detail(order_id: int, admin: dict = Depends(require_support_access)):
    order = await OrderAdminService.get_order_detail(admin["shop_id"], order_id)

    if order is None:
        return {"ok": False, "error": "Не найден"}

    return order


@router.patch("/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    body: UpdateOrderStatusBody,
    admin: dict = Depends(require_support_access),
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
async def list_users(admin: dict = Depends(require_support_access)):
    return await OrderAdminService.get_users(admin["shop_id"])


# ==========================
# Промокоды
# ==========================

@router.get("/promos")
async def list_promos(admin: dict = Depends(require_active_subscription)):
    return await PromoCodeService.get_all(admin["shop_id"])


@router.post("/promos")
async def create_promo(body: CreatePromoBody, admin: dict = Depends(require_catalog_access)):
    promo_id = await PromoCodeService.create(
        admin["shop_id"],
        code=body.code,
        discount_type=body.discount_type,
        discount_value=body.discount_value,
        max_uses=body.max_uses,
    )
    return {"id": promo_id}


@router.patch("/promos/{promo_id}/toggle")
async def toggle_promo(promo_id: int, admin: dict = Depends(require_catalog_access)):
    await PromoCodeService.toggle_active(admin["shop_id"], promo_id)
    return {"ok": True}


@router.delete("/promos/{promo_id}")
async def delete_promo(promo_id: int, admin: dict = Depends(require_catalog_access)):
    await PromoCodeService.delete(admin["shop_id"], promo_id)
    return {"ok": True}


# ==========================
# Отзывы
# ==========================

@router.get("/reviews")
async def list_reviews(admin: dict = Depends(require_support_access)):
    return await ReviewAdminService.get_all_reviews(admin["shop_id"])


@router.delete("/reviews/{review_id}")
async def delete_review(review_id: int, admin: dict = Depends(require_support_access)):
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
async def update_message(key: str, body: UpdateMessageBody, admin: dict = Depends(require_catalog_access)):
    await MessageService.update(admin["shop_id"], key, body.content)
    return {"ok": True}


@router.post("/settings/messages/{key}/reset")
async def reset_message(key: str, admin: dict = Depends(require_catalog_access)):
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
async def update_delivery_settings(body: UpdateDeliveryBody, admin: dict = Depends(require_catalog_access)):
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
    return {
        "attrs": await ProductAttrService.list_defs(admin["shop_id"]),
    }


@router.post("/settings/product-attrs")
async def create_product_attr(body: CreateAttrDefBody, admin: dict = Depends(require_catalog_access)):
    return await ProductAttrService.create_def(admin["shop_id"], body.label)


@router.put("/settings/product-attrs/{attr_id}")
async def update_product_attr(
    attr_id: int,
    body: UpdateAttrDefBody,
    admin: dict = Depends(require_catalog_access),
):
    result = await ProductAttrService.update_def(
        admin["shop_id"], attr_id, label=body.label, position=body.position,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Характеристика не найдена")
    return result


@router.delete("/settings/product-attrs/{attr_id}")
async def delete_product_attr(attr_id: int, admin: dict = Depends(require_catalog_access)):
    ok = await ProductAttrService.delete_def(admin["shop_id"], attr_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Характеристика не найдена")
    return {"ok": True}


# ==========================
# Настройки (реквизиты)
# ==========================

@router.get("/settings/company")
async def get_company_info(admin: dict = Depends(require_owner)):
    shop = await ShopService.get(admin["shop_id"])
    return {
        "company_name": shop["company_name"] if shop else None,
        "company_inn": shop["company_inn"] if shop else None,
        "company_address": shop["company_address"] if shop else None,
        "legal_type": shop["legal_type"] if shop else "individual",
    }


@router.put("/settings/company")
async def update_company_info(body: UpdateCompanyInfoBody, admin: dict = Depends(require_owner)):
    await ShopService.update_company_info(
        admin["shop_id"],
        body.company_name,
        body.company_inn,
        body.company_address,
        legal_type=body.legal_type,
    )
    return {"ok": True}


# ==========================
# Настройки (название магазина)
# ==========================

@router.get("/settings/shop")
async def get_shop_info(admin: dict = Depends(require_active_subscription)):
    shop = await ShopService.get(admin["shop_id"])
    return {
        "name": shop["name"] if shop else None,
    }


@router.put("/settings/shop")
async def update_shop_name(body: UpdateShopNameBody, admin: dict = Depends(require_owner)):
    name = body.name.strip()
    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="Название должно содержать от 1 до 100 символов")
    result = await ShopService.update(admin["shop_id"], name=name)
    if result is None:
        logger.warning("Shop not found for update: shop_id=%s", admin["shop_id"])
        raise HTTPException(status_code=404, detail="Магазин не найден")
    logger.info(
        "Shop name updated: shop_id=%s, new_name=%r",
        admin["shop_id"], result["name"],
    )
    return {"ok": True}


# ==========================
# Настройки (платежи магазина)
# ==========================

@router.get("/settings/payments")
async def get_shop_payment_settings(admin: dict = Depends(require_owner)):
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
    admin: dict = Depends(require_owner_recent),
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
# Настройки (юридические документы магазина)
# ==========================

@router.get("/settings/legal")
async def get_legal_docs(admin: dict = Depends(require_owner)):
    shop = await ShopService.get(admin["shop_id"])
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    return {
        "offer_text": shop.get("offer_text"),
        "privacy_policy_text": shop.get("privacy_policy_text"),
    }


@router.put("/settings/legal")
async def update_legal_docs(
    body: UpdateLegalDocsBody,
    admin: dict = Depends(require_owner),
):
    result = await ShopService.update_legal_docs(
        admin["shop_id"],
        offer_text=body.offer_text,
        privacy_policy_text=body.privacy_policy_text,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    logger.info(
        "Legal docs updated: shop_id=%s",
        admin["shop_id"],
    )
    return {"ok": True}


@router.post("/settings/legal/generate")
async def generate_legal_template(admin: dict = Depends(require_owner)):
    template = await ShopService.generate_offer_template(admin["shop_id"])
    return template


# ==========================
# Настройки (тема оформления TMA)
# ==========================

@router.get("/settings/theme")
async def get_shop_theme(admin: dict = Depends(require_active_subscription)):
    shop = await ShopService.get(admin["shop_id"])
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop["theme"]


@router.put("/settings/theme")
async def update_shop_theme(
    body: UpdateThemeBody,
    admin: dict = Depends(require_catalog_access),
):
    result = await ShopService.update_theme(
        admin["shop_id"],
        primary_color=body.primary_color,
        bg_color=body.bg_color,
        text_color=body.text_color,
        button_text_color=body.button_text_color,
        secondary_bg_color=body.secondary_bg_color,
        radius=body.radius,
        font_family=body.font_family,
        price_color=body.price_color,
        price_size=body.price_size,
        price_weight=body.price_weight,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    return {"ok": True}


# ==========================
# Правовые документы (системный шаблон + дополнение продавца)
# ==========================

@router.get("/settings/legal-documents")
async def get_legal_documents(admin: dict = Depends(require_owner)):
    docs = await LegalDocumentService.get_all_documents(admin["shop_id"])
    if docs is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    return docs


@router.put("/settings/legal-documents/{document_type}")
async def update_seller_addendum(
    document_type: str,
    body: UpdateSellerAddendumBody,
    admin: dict = Depends(require_owner),
):
    if document_type not in LEGAL_DOCUMENT_TITLES:
        raise HTTPException(status_code=400, detail="Неизвестный тип документа")
    if document_type == "data_processing_mandate":
        raise HTTPException(status_code=403, detail="Документ формируется автоматически и не редактируется")

    await LegalDocumentService.update_seller_addendum(
        admin["shop_id"], document_type, body.seller_addendum
    )
    logger.info(
        "Seller addendum updated: shop_id=%s, doc_type=%s",
        admin["shop_id"], document_type,
    )
    return {"ok": True}


# ==========================
# Роскомнадзор — уведомление об обработке ПДн
# ==========================

@router.get("/settings/roskomnadzor")
async def get_roskomnadzor_info(admin: dict = Depends(require_active_subscription)):
    shop = await ShopService.get(admin["shop_id"])
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    return {
        "legal_type": shop.get("legal_type", "individual"),
        "company_name": shop.get("company_name"),
        "company_inn": shop.get("company_inn"),
        "info": (
            "При сборе персональных данных через корзину/форму заказа оператор\n"
            "обязан направить уведомление об обработке ПДн в территориальный орган\n"
            "Роскомнадзора (ст. 22 ФЗ-152 «О персональных данных»)."
        ),
        "official_url": "https://pd.rkn.gov.ru/owners/notification/",
    }


@router.get("/settings/roskomnadzor/draft")
async def download_roskomnadzor_draft(admin: dict = Depends(require_active_subscription)):
    shop = await ShopService.get(admin["shop_id"])
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found")

    draft = LegalDocumentService.get_roskomnadzor_draft(shop)
    filename = f"rkn_notification_{shop.get('legal_type', 'individual')}.txt"
    return Response(
        content=draft,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ==========================
# Администраторы
# ==========================

@router.get("/admins")
async def list_admins(admin: dict = Depends(require_owner)):
    return await AdminUserService.get_all(admin["shop_id"])


@router.post("/admins")
async def create_admin(body: CreateAdminBody, admin: dict = Depends(require_owner)):
    admin_id = await AdminUserService.add(
        admin["shop_id"], body.telegram_user_id, body.display_name, body.role
    )
    return {"id": admin_id}


@router.delete("/admins/{admin_id}")
async def delete_admin(admin_id: int, admin: dict = Depends(require_owner)):
    if admin_id < 0:
        raise HTTPException(status_code=400, detail="Нельзя удалить супер-админа из .env")

    admin_to_delete = await AdminUserService.get(admin["shop_id"], admin_id)
    if admin_to_delete is None:
        raise HTTPException(status_code=404, detail="Администратор не найден")

    if admin_to_delete["telegram_user_id"] == admin["admin_id"]:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

    if await AdminUserService.count_admins(admin["shop_id"]) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить последнего администратора магазина",
        )

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
    admin: dict = Depends(require_support_access),
):
    return await CrmService.get_users(admin["shop_id"], search, tag, page, per_page)


@router.get("/crm/users/{telegram_user_id}")
async def crm_user_detail(telegram_user_id: int, admin: dict = Depends(require_support_access)):
    detail = await CrmService.get_user_detail(admin["shop_id"], telegram_user_id)
    if detail is None:
        return {"ok": False, "error": "Пользователь не найден"}
    return detail


@router.put("/crm/users/{telegram_user_id}/notes")
async def crm_update_notes(
    telegram_user_id: int,
    body: UpdateNotesBody,
    admin: dict = Depends(require_support_access),
):
    ok = await CrmService.update_notes(admin["shop_id"], telegram_user_id, body.notes)
    return {"ok": ok}


@router.put("/crm/users/{telegram_user_id}/phone")
async def crm_update_phone(
    telegram_user_id: int,
    body: UpdatePhoneBody,
    admin: dict = Depends(require_support_access),
):
    ok = await CrmService.update_phone(admin["shop_id"], telegram_user_id, body.phone)
    return {"ok": ok}


@router.post("/crm/users/{telegram_user_id}/tags")
async def crm_add_tag(
    telegram_user_id: int,
    body: AddTagBody,
    admin: dict = Depends(require_support_access),
):
    ok = await CrmService.add_tag(admin["shop_id"], telegram_user_id, body.tag)
    return {"ok": ok}


@router.delete("/crm/users/{telegram_user_id}/tags/{tag}")
async def crm_remove_tag(
    telegram_user_id: int,
    tag: str,
    admin: dict = Depends(require_support_access),
):
    ok = await CrmService.remove_tag(admin["shop_id"], telegram_user_id, tag)
    return {"ok": ok}


@router.get("/crm/tags")
async def crm_all_tags(admin: dict = Depends(require_support_access)):
    return await CrmService.get_all_tags(admin["shop_id"])


# ==========================
# CRM — История коммуникации
# ==========================

@router.get("/crm/users/{telegram_user_id}/messages")
async def crm_messages(
    telegram_user_id: int,
    page: int = 1,
    per_page: int = 50,
    admin: dict = Depends(require_support_access),
):
    return await CrmService.get_communication_history(admin["shop_id"], telegram_user_id, page, per_page)


@router.post("/crm/users/{telegram_user_id}/send")
async def crm_send_message(
    telegram_user_id: int,
    body: SendMessageBody,
    admin: dict = Depends(require_support_access),
):
    bot = get_bot(admin["shop_id"])
    if bot is None:
        return {"ok": False, "error": "Бот недоступен"}

    text = body.text.strip()
    if not text:
        return {"ok": False, "error": "Пустое сообщение"}

    try:
        await bot.send_message(telegram_user_id, text, parse_mode=None)
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
    admin: dict = Depends(require_catalog_access),
):
    return await BroadcastService.get_broadcasts(admin["shop_id"], page, per_page)


@router.get("/broadcasts/{broadcast_id}")
async def get_broadcast(broadcast_id: int, admin: dict = Depends(require_catalog_access)):
    broadcast = await BroadcastService.get_broadcast(admin["shop_id"], broadcast_id)
    if broadcast is None:
        return {"ok": False, "error": "Рассылка не найдена"}
    return broadcast


@router.post("/broadcasts/preview")
async def preview_recipients(
    body: PreviewRecipientsBody,
    admin: dict = Depends(require_catalog_access),
):
    return await BroadcastService.preview_recipients(admin["shop_id"], body.tags)


@router.post("/broadcasts")
async def create_broadcast(
    body: CreateBroadcastBody,
    admin: dict = Depends(require_catalog_access),
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
    admin: dict = Depends(require_catalog_access),
):
    bot = get_bot(admin["shop_id"])
    if bot is None:
        return {"ok": False, "error": "Бот недоступен"}

    result = await BroadcastService.send_broadcast(admin["shop_id"], broadcast_id, bot)
    return result
