"""Regression tests for the security audit findings."""

from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import UploadFile

from app.api.admin_auth import _check_role
from app.api.auth import get_current_user
from app.api.main import create_app
from app.api.routes.admin import (
    CreateCategoryBody,
    MAX_PHOTO_FILE_SIZE,
    _read_upload_with_limit,
    _validate_image_upload,
)
from app.database.db import async_session
from app.models.broadcast import Broadcast
from app.models.cart_item import CartItem
from app.models.category import Category
from app.models.order import Order
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.shop import Shop
from app.services.broadcast_service import BroadcastService
from app.services.cart_service import CartService
from app.services.catalog_import_service import _validate_xlsx_archive
from app.services.order_service import OrderService
from app.utils.crypto import encrypt, token_hash
from app.utils.escape import sanitize_telegram_html


ROOT = Path(__file__).resolve().parents[1]


async def _seed_second_shop(db_session) -> None:
    async with db_session() as session:
        session.add(
            Shop(
                id=2,
                name="Second",
                bot_token=encrypt("second:test-token"),
                bot_token_hash=token_hash("second:test-token"),
                owner_telegram_id=222,
            )
        )
        session.add(Category(id=20, shop_id=2, name="Other", emoji="📦"))
        session.add(
            Product(
                id=20,
                shop_id=2,
                category_id=20,
                name="Other product",
                description="tenant two",
                variants=[
                    ProductVariant(
                        id=20,
                        shop_id=2,
                        volume="one",
                        price=500,
                        stock=10,
                    )
                ],
            )
        )
        await session.commit()


class TestStoredXssHardening:
    def test_telegram_html_allows_formatting_but_escapes_links_and_attributes(self):
        content = '<b>Safe</b><a href="https://evil.test">click</a><i onclick="x">x</i>'
        sanitized = sanitize_telegram_html(content)
        assert sanitized.startswith("<b>Safe</b>")
        assert "<a " not in sanitized
        assert "href=" in sanitized
        assert "<i " not in sanitized

    def test_category_emoji_rejects_markup(self):
        with pytest.raises(ValidationError):
            CreateCategoryBody(
                name="Injected",
                emoji='<img src=x onerror=alert(document.domain)>',
            )

    def test_category_emoji_accepts_unicode_emoji(self):
        assert CreateCategoryBody(name="Clothes", emoji="👗").emoji == "👗"

    def test_miniapp_has_no_inline_event_handlers_or_scripts(self):
        index = (ROOT / "app/api/static/index.html").read_text(encoding="utf-8")
        app_js = (ROOT / "app/api/static/app.js").read_text(encoding="utf-8")
        lowered = (index + app_js).lower()
        for handler in ("onclick=", "onerror=", "onchange=", "onsubmit=", "onscroll="):
            assert handler not in lowered
        assert "<script>" not in index.lower()

    def test_miniapp_csp_blocks_inline_scripts(self):
        caddy = (ROOT / "Caddyfile").read_text(encoding="utf-8")
        miniapp = caddy.split("(miniapp_security_headers)", 1)[1].split("}\n", 1)[0]
        script_policy = miniapp.split("script-src", 1)[1].split(";", 1)[0]
        assert "'self'" in script_policy
        assert "'unsafe-inline'" not in script_policy


class TestCartAndOrderIntegrity:
    @pytest.mark.parametrize("quantity", [-10, 0, 101])
    async def test_service_rejects_invalid_quantity(
        self, db_session, seed_data, quantity
    ):
        error = await CartService.add_item(1, 777, 1, 1, quantity)
        assert error is not None
        async with db_session() as session:
            count = (
                await session.execute(
                    select(func.count()).select_from(CartItem).where(
                        CartItem.telegram_user_id == 777
                    )
                )
            ).scalar_one()
            assert count == 0

    async def test_mismatched_product_and_variant_are_rejected(
        self, db_session, seed_data
    ):
        error = await CartService.add_item(1, 777, product_id=3, variant_id=1)
        assert error is not None

    async def test_cross_tenant_variant_is_rejected(self, db_session, seed_data):
        await _seed_second_shop(db_session)
        error = await CartService.add_item(1, 777, product_id=1, variant_id=20)
        assert error is not None

    async def test_database_rejects_nonpositive_cart_quantity(
        self, db_session, seed_data
    ):
        async with db_session() as session:
            session.add(
                CartItem(
                    shop_id=1,
                    telegram_user_id=777,
                    product_id=1,
                    variant_id=1,
                    quantity=0,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()

    async def test_disabled_manual_payment_creates_no_order(
        self, db_session, seed_data
    ):
        async with db_session() as session:
            shop = await session.get(Shop, 1)
            shop.manual_payment_enabled = False
            await session.commit()

        app = create_app()

        async def current_user():
            return {"id": 777, "shop_id": 1}

        app.dependency_overrides[get_current_user] = current_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/shop/orders",
                json={
                    "full_name": "Test User",
                    "phone": "+79990000000",
                    "payment_method": "manual",
                },
            )
        assert response.status_code == 400
        async with db_session() as session:
            count = (
                await session.execute(
                    select(func.count()).select_from(Order).where(
                        Order.telegram_user_id == 777
                    )
                )
            ).scalar_one()
            assert count == 0

    async def test_active_unpaid_order_limit(self, db_session, seed_data):
        for _ in range(OrderService.MAX_ACTIVE_UNPAID_PER_USER):
            assert await CartService.add_item(1, 777, 1, 1, 1) is None
            created = await OrderService.create_order(
                1, 777, "Test User", "+79990000000", "", payment_method="manual"
            )
            assert created and "error" not in created

        assert await CartService.add_item(1, 777, 1, 1, 1) is None
        blocked = await OrderService.create_order(
            1, 777, "Test User", "+79990000000", "", payment_method="manual"
        )
        assert blocked == {"error": "too_many_unpaid_orders"}

    async def test_expired_reservation_releases_stock_once(
        self, db_session, seed_data
    ):
        assert await CartService.add_item(1, 777, 1, 1, 2) is None
        created = await OrderService.create_order(
            1, 777, "Test User", "+79990000000", "", payment_method="manual"
        )
        async with db_session() as session:
            order = await session.get(Order, created["order_id"])
            order.stock_reserved_until = datetime.now() - timedelta(minutes=1)
            order.created_at = datetime.now() - timedelta(minutes=21)
            order.status_updated_at = datetime.now() - timedelta(minutes=21)
            await session.commit()

        assert await OrderService.auto_cancel_stale_orders(minutes=20) == 1
        assert await OrderService.auto_cancel_stale_orders(minutes=20) == 0
        async with db_session() as session:
            assert (await session.get(ProductVariant, 1)).stock == 10


class TestTenantAndAuthorizationBoundaries:
    async def test_broadcast_cannot_use_another_shops_product(
        self, db_session, seed_data
    ):
        await _seed_second_shop(db_session)
        with pytest.raises(ValueError):
            await BroadcastService.create_broadcast(1, product_id=20, discount_percent=10)

    async def test_broadcast_cannot_send_another_shops_record(
        self, db_session, seed_data
    ):
        await _seed_second_shop(db_session)
        async with db_session() as session:
            broadcast = Broadcast(
                shop_id=2,
                product_id=20,
                product_name="Other product",
                original_price=500,
                discounted_price=450,
                discount_percent=10,
            )
            session.add(broadcast)
            await session.commit()
            await session.refresh(broadcast)
            broadcast_id = broadcast.id

        result = await BroadcastService.send_broadcast(1, broadcast_id, AsyncMock())
        assert result["ok"] is False
        async with db_session() as session:
            assert (await session.get(Broadcast, broadcast_id)).status == "draft"

    def test_content_role_cannot_perform_owner_action(self):
        with pytest.raises(Exception) as exc_info:
            _check_role({"role": "content", "is_super_admin": False}, {"owner"})
        assert getattr(exc_info.value, "status_code", None) == 403

    async def test_subscription_state_and_payment_require_admin_cookie(self):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            current = await client.get("/api/subscriptions/current")
            payment = await client.post(
                "/api/subscriptions/pay", json={"plan_id": 1}
            )
        assert current.status_code == 401
        assert payment.status_code == 401


class TestUploadAndDeploymentHardening:
    def test_invalid_image_is_rejected(self):
        with pytest.raises(ValueError):
            _validate_image_upload(b"not-an-image")

    async def test_streaming_upload_limit(self):
        upload = UploadFile(
            filename="large.jpg",
            file=BytesIO(b"x" * 1025),
        )
        with pytest.raises(Exception) as exc_info:
            await _read_upload_with_limit(upload, max_size=1024, chunk_size=256)
        assert getattr(exc_info.value, "status_code", None) == 413

    def test_xlsx_high_compression_ratio_is_rejected(self):
        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("xl/worksheets/sheet1.xml", b"0" * 1_000_000)
        with pytest.raises(ValueError, match="коэффициент сжатия"):
            _validate_xlsx_archive(buffer.getvalue())

    def test_secure_dependency_versions_and_no_default_database_password(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        assert "aiohttp==3.14.3" in requirements
        assert "cryptography==46.0.7" in requirements
        assert "POSTGRES_PASSWORD:-changeme" not in compose
        assert "POSTGRES_PASSWORD:?" in compose
