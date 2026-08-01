from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel
from aiogram.types import BufferedInputFile

from app.api.admin_auth import require_admin
from app.bot.bot import get_bot
from app.core.config import settings as app_settings
from app.database.db import async_session
from app.models.product import Product
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_service import AdminService
from app.services.admin_user_service import AdminUserService
from app.services.catalog_service import CatalogService
from app.services.message_service import MessageService, DEFAULT_MESSAGES, MESSAGE_LABELS
from app.services.promo_service import PromoCodeService
from app.services.review_service import ReviewService
from app.services.crm_service import CrmService
from app.services.broadcast_service import BroadcastService
from app.utils.order_status import STATUS_LABELS

router = APIRouter()


# ==========================
# Pydantic схемы
# ==========================

class RequestCodeBody(BaseModel):
    telegram_user_id: int


class VerifyCodeBody(BaseModel):
    telegram_user_id: int
    code: str


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


class UpdateOrderStatusBody(BaseModel):
    status: str


class CreatePromoBody(BaseModel):
    code: str
    discount_type: str
    discount_value: int
    max_uses: int | None = None


class UpdateMessageBody(BaseModel):
    content: str


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


class PreviewRecipientsBody(BaseModel):
    tags: list[str] | None = None


# ==========================
# Auth
# ==========================

@router.post("/auth/request-code")
async def request_code(body: RequestCodeBody):
    ok = await AdminAuthService.request_code(body.telegram_user_id)

    if not ok:
        return {"ok": False, "error": "Пользователь не является администратором"}

    return {"ok": True}


@router.post("/auth/verify")
async def verify_code(body: VerifyCodeBody):
    token = AdminAuthService.verify_code(body.telegram_user_id, body.code)

    if token is None:
        return {"ok": False, "error": "Неверный или истекший код"}

    return {"ok": True, "token": token}


@router.get("/auth/me")
async def get_me(admin_id: int = Depends(require_admin)):
    return {"telegram_user_id": admin_id}


# ==========================
# Dashboard / Статистика
# ==========================

@router.get("/stats")
async def get_stats(_admin_id: int = Depends(require_admin)):
    stats = await AdminService.get_stats()
    return stats


@router.get("/analytics/revenue")
async def get_revenue_chart(days: int = 30, _admin_id: int = Depends(require_admin)):
    return await AdminService.get_revenue_chart(days)


@router.get("/analytics/overview")
async def get_analytics_overview(days: int = 30, _admin_id: int = Depends(require_admin)):
    return await AdminService.get_analytics_overview(days)


@router.get("/analytics/categories")
async def get_category_breakdown(days: int = 30, _admin_id: int = Depends(require_admin)):
    return await AdminService.get_category_breakdown(days)


@router.get("/analytics/products")
async def get_product_stats(days: int = 30, _admin_id: int = Depends(require_admin)):
    return await AdminService.get_product_stats(days)


@router.get("/analytics/customers")
async def get_customer_stats(days: int = 30, _admin_id: int = Depends(require_admin)):
    return await AdminService.get_customer_stats(days)


@router.get("/analytics/promos")
async def get_promo_stats(days: int = 30, _admin_id: int = Depends(require_admin)):
    return await AdminService.get_promo_stats(days)


@router.get("/analytics/reviews")
async def get_review_stats(_admin_id: int = Depends(require_admin)):
    return await AdminService.get_review_stats()


# ==========================
# Категории
# ==========================

@router.get("/categories")
async def list_categories(_admin_id: int = Depends(require_admin)):
    return await AdminService.get_categories()


@router.post("/categories")
async def create_category(body: CreateCategoryBody, _admin_id: int = Depends(require_admin)):
    category_id = await AdminService.create_category(body.name, body.emoji)
    return {"id": category_id}


@router.put("/categories/{category_id}")
async def update_category(category_id: int, body: UpdateCategoryBody, _admin_id: int = Depends(require_admin)):
    if body.name is not None:
        await AdminService.rename_category(category_id, body.name)
    if body.emoji is not None:
        await AdminService.update_category_emoji(category_id, body.emoji)
    return {"ok": True}


@router.delete("/categories/{category_id}")
async def delete_category(category_id: int, _admin_id: int = Depends(require_admin)):
    ok = await AdminService.delete_category(category_id)

    if not ok:
        return {"ok": False, "error": "В категории есть товары"}

    return {"ok": True}


# ==========================
# Товары
# ==========================

@router.get("/products")
async def list_products(category_id: int | None = None, _admin_id: int = Depends(require_admin)):
    if category_id is not None:
        return await AdminService.get_products(category_id)
    return await AdminService.get_all_products()


@router.get("/products/{product_id}")
async def get_product(product_id: int, _admin_id: int = Depends(require_admin)):
    product = await AdminService.get_product(product_id)

    if product is None:
        return {"ok": False, "error": "Не найден"}

    return product


@router.post("/products")
async def create_product(body: CreateProductBody, _admin_id: int = Depends(require_admin)):
    product_id = await AdminService.create_product(
        category_id=body.category_id,
        name=body.name,
        description=body.description,
        variants=[v.model_dump() for v in body.variants],
    )
    return {"id": product_id}


@router.put("/products/{product_id}")
async def update_product(product_id: int, body: UpdateProductBody, _admin_id: int = Depends(require_admin)):
    await AdminService.update_product(
        product_id,
        name=body.name,
        description=body.description,
    )

    if body.category_id is not None:
        async with async_session() as session:
            product = await session.get(Product, product_id)
            if product:
                product.category_id = body.category_id
                await session.commit()

    if body.is_active is not None:
        await AdminService.toggle_active(product_id)

    return {"ok": True}


@router.delete("/products/{product_id}")
async def delete_product(product_id: int, _admin_id: int = Depends(require_admin)):
    await AdminService.delete_product(product_id)
    return {"ok": True}


@router.patch("/products/{product_id}/toggle")
async def toggle_product(product_id: int, _admin_id: int = Depends(require_admin)):
    is_active = await AdminService.toggle_active(product_id)
    return {"is_active": is_active}


@router.post("/products/{product_id}/photos")
async def upload_photo(
    product_id: int,
    file: UploadFile = File(...),
    admin_id: int = Depends(require_admin),
):
    content = await file.read()

    bot = get_bot()
    if bot is None:
        return {"ok": False, "error": "Бот недоступен"}

    input_file = BufferedInputFile(content, file.filename or "photo.jpg")
    msg = await bot.send_photo(admin_id, input_file)

    file_id = msg.photo[-1].file_id

    await bot.delete_message(admin_id, msg.message_id)

    photo_id = await AdminService.add_photo(product_id, file_id)

    return {"id": photo_id, "file_id": file_id}


@router.delete("/products/{product_id}/photos/{photo_id}")
async def delete_photo(product_id: int, photo_id: int, _admin_id: int = Depends(require_admin)):
    await AdminService.delete_photo(photo_id)
    return {"ok": True}


# ==========================
# Заказы
# ==========================

@router.get("/orders")
async def list_orders(
    status: str | None = None,
    page: int = 1,
    per_page: int = 20,
    _admin_id: int = Depends(require_admin),
):
    return await AdminService.get_orders_filtered(status, page, per_page)


@router.get("/orders/{order_id}")
async def get_order_detail(order_id: int, _admin_id: int = Depends(require_admin)):
    order = await AdminService.get_order_detail(order_id)

    if order is None:
        return {"ok": False, "error": "Не найден"}

    return order


@router.patch("/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    body: UpdateOrderStatusBody,
    _admin_id: int = Depends(require_admin),
):
    await AdminService.set_order_status(order_id, body.status)
    return {"ok": True}


@router.get("/statuses")
async def get_statuses(_admin_id: int = Depends(require_admin)):
    return [{"value": k, "label": v} for k, v in STATUS_LABELS.items()]


# ==========================
# Пользователи
# ==========================

@router.get("/users")
async def list_users(_admin_id: int = Depends(require_admin)):
    return await AdminService.get_users()


# ==========================
# Промокоды
# ==========================

@router.get("/promos")
async def list_promos(_admin_id: int = Depends(require_admin)):
    return await PromoCodeService.get_all()


@router.post("/promos")
async def create_promo(body: CreatePromoBody, _admin_id: int = Depends(require_admin)):
    promo_id = await PromoCodeService.create(
        code=body.code,
        discount_type=body.discount_type,
        discount_value=body.discount_value,
        max_uses=body.max_uses,
    )
    return {"id": promo_id}


@router.patch("/promos/{promo_id}/toggle")
async def toggle_promo(promo_id: int, _admin_id: int = Depends(require_admin)):
    await PromoCodeService.toggle_active(promo_id)
    return {"ok": True}


@router.delete("/promos/{promo_id}")
async def delete_promo(promo_id: int, _admin_id: int = Depends(require_admin)):
    await PromoCodeService.delete(promo_id)
    return {"ok": True}


# ==========================
# Отзывы
# ==========================

@router.get("/reviews")
async def list_reviews(_admin_id: int = Depends(require_admin)):
    return await AdminService.get_all_reviews()


@router.delete("/reviews/{review_id}")
async def delete_review(review_id: int, _admin_id: int = Depends(require_admin)):
    ok = await AdminService.delete_review(review_id)
    return {"ok": ok}


# ==========================
# Настройки (сообщения)
# ==========================

@router.get("/settings/messages")
async def list_messages(_admin_id: int = Depends(require_admin)):
    return await MessageService.get_all()


@router.get("/settings/messages/{key}")
async def get_message(key: str, _admin_id: int = Depends(require_admin)):
    msg = await MessageService.get_one(key)

    if msg is None:
        return {"ok": False, "error": "Не найдено"}

    return msg


@router.put("/settings/messages/{key}")
async def update_message(key: str, body: UpdateMessageBody, _admin_id: int = Depends(require_admin)):
    await MessageService.update(key, body.content)
    return {"ok": True}


@router.post("/settings/messages/{key}/reset")
async def reset_message(key: str, _admin_id: int = Depends(require_admin)):
    await MessageService.reset(key)
    return {"ok": True}


@router.get("/settings/payment")
async def get_payment_settings(_admin_id: int = Depends(require_admin)):
    return {
        "payment_card_number": app_settings.payment_card_number,
        "payment_recipient_name": app_settings.payment_recipient_name,
        "tinkoff_enabled": app_settings.tinkoff_enabled,
    }


# ==========================
# Администраторы
# ==========================

@router.get("/admins")
async def list_admins(_admin_id: int = Depends(require_admin)):
    return await AdminUserService.get_all()


@router.post("/admins")
async def create_admin(body: CreateAdminBody, _admin_id: int = Depends(require_admin)):
    admin_id = await AdminUserService.add(body.telegram_user_id, body.display_name)
    return {"id": admin_id}


@router.delete("/admins/{admin_id}")
async def delete_admin(admin_id: int, _admin_id: int = Depends(require_admin)):
    if admin_id < 0:
        return {"ok": False, "error": "Нельзя удалить супер-админа из .env"}
    ok = await AdminUserService.delete(admin_id)
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
    _admin_id: int = Depends(require_admin),
):
    return await CrmService.get_users(search, tag, page, per_page)


@router.get("/crm/users/{telegram_user_id}")
async def crm_user_detail(telegram_user_id: int, _admin_id: int = Depends(require_admin)):
    detail = await CrmService.get_user_detail(telegram_user_id)
    if detail is None:
        return {"ok": False, "error": "Пользователь не найден"}
    return detail


@router.put("/crm/users/{telegram_user_id}/notes")
async def crm_update_notes(
    telegram_user_id: int,
    body: UpdateNotesBody,
    _admin_id: int = Depends(require_admin),
):
    ok = await CrmService.update_notes(telegram_user_id, body.notes)
    return {"ok": ok}


@router.put("/crm/users/{telegram_user_id}/phone")
async def crm_update_phone(
    telegram_user_id: int,
    body: UpdatePhoneBody,
    _admin_id: int = Depends(require_admin),
):
    ok = await CrmService.update_phone(telegram_user_id, body.phone)
    return {"ok": ok}


@router.post("/crm/users/{telegram_user_id}/tags")
async def crm_add_tag(
    telegram_user_id: int,
    body: AddTagBody,
    _admin_id: int = Depends(require_admin),
):
    ok = await CrmService.add_tag(telegram_user_id, body.tag)
    return {"ok": ok}


@router.delete("/crm/users/{telegram_user_id}/tags/{tag}")
async def crm_remove_tag(
    telegram_user_id: int,
    tag: str,
    _admin_id: int = Depends(require_admin),
):
    ok = await CrmService.remove_tag(telegram_user_id, tag)
    return {"ok": ok}


@router.get("/crm/tags")
async def crm_all_tags(_admin_id: int = Depends(require_admin)):
    return await CrmService.get_all_tags()


# ==========================
# CRM — История коммуникации
# ==========================

@router.get("/crm/users/{telegram_user_id}/messages")
async def crm_messages(
    telegram_user_id: int,
    page: int = 1,
    per_page: int = 50,
    _admin_id: int = Depends(require_admin),
):
    return await CrmService.get_communication_history(telegram_user_id, page, per_page)


@router.post("/crm/users/{telegram_user_id}/send")
async def crm_send_message(
    telegram_user_id: int,
    body: SendMessageBody,
    admin_id: int = Depends(require_admin),
):
    bot = get_bot()
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
        telegram_user_id=telegram_user_id,
        direction="out",
        message_type="text",
        text=text,
        admin_id=admin_id,
    )
    return {"ok": True}


# ==========================
# Рассылки
# ==========================

@router.get("/broadcasts")
async def list_broadcasts(
    page: int = 1,
    per_page: int = 20,
    _admin_id: int = Depends(require_admin),
):
    return await BroadcastService.get_broadcasts(page, per_page)


@router.get("/broadcasts/{broadcast_id}")
async def get_broadcast(broadcast_id: int, _admin_id: int = Depends(require_admin)):
    broadcast = await BroadcastService.get_broadcast(broadcast_id)
    if broadcast is None:
        return {"ok": False, "error": "Рассылка не найдена"}
    return broadcast


@router.post("/broadcasts/preview")
async def preview_recipients(
    body: PreviewRecipientsBody,
    _admin_id: int = Depends(require_admin),
):
    return await BroadcastService.preview_recipients(body.tags)


@router.post("/broadcasts")
async def create_broadcast(
    body: CreateBroadcastBody,
    admin_id: int = Depends(require_admin),
):
    try:
        broadcast = await BroadcastService.create_broadcast(
            product_id=body.product_id,
            discount_percent=body.discount_percent,
            filter_tags=body.filter_tags,
            variant_id=body.variant_id,
            message_text=body.message_text,
            created_by=admin_id,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "broadcast_id": broadcast.id}


@router.post("/broadcasts/{broadcast_id}/send")
async def send_broadcast(
    broadcast_id: int,
    admin_id: int = Depends(require_admin),
):
    bot = get_bot()
    if bot is None:
        return {"ok": False, "error": "Бот недоступен"}

    result = await BroadcastService.send_broadcast(broadcast_id, bot)
    return result
