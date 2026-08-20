from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.services.catalog_admin_service import CatalogAdminService
from app.services.product_lifecycle_service import ProductLifecycleService


async def _set_product_stock(db_session, product_id: int, stock: int) -> None:
    async with db_session() as session:
        product = await session.get(Product, product_id)
        variants = (
            await session.execute(
                ProductVariant.__table__.select().where(
                    ProductVariant.product_id == product_id
                )
            )
        ).all()
        for row in variants:
            variant = await session.get(ProductVariant, row.id)
            variant.stock = stock
        product.out_of_stock_since = None
        product.auto_hidden_at = None
        product.lifecycle_deleted_at = None
        product.is_active = True
        await session.commit()


class TestProductLifecycleService:
    async def test_starts_timer_then_hides_after_seven_days(
        self, db_session, seed_data
    ):
        started_at = datetime(2026, 8, 20, 10, 0, 0)
        await _set_product_stock(db_session, 1, 0)

        started = await ProductLifecycleService.reconcile(
            product_ids=[1], now=started_at
        )
        assert started["started"] == 1

        before_hide = await ProductLifecycleService.reconcile(
            product_ids=[1], now=started_at + timedelta(days=6, hours=23)
        )
        assert before_hide["hidden"] == 0

        hidden = await ProductLifecycleService.reconcile(
            product_ids=[1], now=started_at + timedelta(days=7)
        )
        assert hidden["hidden"] == 1

        admin_product = await CatalogAdminService.get_product(1, 1)
        assert admin_product["lifecycle_status"] == "out_of_stock_hidden"
        assert admin_product["auto_delete_at"].endswith("Z")

        async with db_session() as session:
            product = await session.get(Product, 1)
            assert product.is_active is False
            assert product.auto_hidden_at == started_at + timedelta(days=7)

    async def test_duplicate_run_is_idempotent(self, db_session, seed_data):
        started_at = datetime(2026, 8, 1)
        await _set_product_stock(db_session, 1, 0)
        await ProductLifecycleService.reconcile(product_ids=[1], now=started_at)

        first = await ProductLifecycleService.reconcile(
            product_ids=[1], now=started_at + timedelta(days=8)
        )
        second = await ProductLifecycleService.reconcile(
            product_ids=[1], now=started_at + timedelta(days=8, hours=1)
        )

        assert first["hidden"] == 1
        assert second["hidden"] == 0
        assert second["deleted"] == 0

    async def test_restock_restores_only_auto_hidden_product(
        self, db_session, seed_data
    ):
        started_at = datetime(2026, 8, 1)
        await _set_product_stock(db_session, 1, 0)
        await ProductLifecycleService.reconcile(product_ids=[1], now=started_at)
        await ProductLifecycleService.reconcile(
            product_ids=[1], now=started_at + timedelta(days=8)
        )

        async with db_session() as session:
            variant = await session.get(ProductVariant, 1)
            variant.stock = 5
            await session.commit()

        restored = await ProductLifecycleService.reconcile(
            product_ids=[1], now=started_at + timedelta(days=9)
        )
        assert restored["restored"] == 1

        async with db_session() as session:
            product = await session.get(Product, 1)
            assert product.is_active is True
            assert product.out_of_stock_since is None
            assert product.auto_hidden_at is None

    async def test_restock_does_not_override_manual_hidden_state(
        self, db_session, seed_data
    ):
        async with db_session() as session:
            product = await session.get(Product, 1)
            product.is_active = False
            product.out_of_stock_since = datetime(2026, 8, 1)
            product.auto_hidden_at = None
            variant = await session.get(ProductVariant, 1)
            variant.stock = 1
            await session.commit()

        result = await ProductLifecycleService.reconcile(
            product_ids=[1], now=datetime(2026, 8, 10)
        )
        assert result["restored"] == 0

        async with db_session() as session:
            product = await session.get(Product, 1)
            assert product.is_active is False
            assert product.out_of_stock_since is None

    async def test_system_deletes_after_thirty_days_but_preserves_row(
        self, db_session, seed_data
    ):
        started_at = datetime(2026, 7, 1)
        await _set_product_stock(db_session, 1, 0)
        await ProductLifecycleService.reconcile(product_ids=[1], now=started_at)

        deleted = await ProductLifecycleService.reconcile(
            product_ids=[1], now=started_at + timedelta(days=30)
        )
        assert deleted["deleted"] == 1
        assert await CatalogAdminService.get_product(1, 1) is None

        async with db_session() as session:
            product = await session.get(Product, 1)
            assert product is not None
            assert product.is_active is False
            assert product.lifecycle_deleted_at == started_at + timedelta(days=30)

    async def test_failure_rolls_back_and_next_run_can_retry(
        self, db_session, seed_data
    ):
        started_at = datetime(2026, 8, 1)
        await _set_product_stock(db_session, 1, 0)
        await ProductLifecycleService.reconcile(product_ids=[1], now=started_at)

        with patch(
            "app.services.product_lifecycle_service."
            "ChannelPostButtonService.enqueue_product_change_in_session",
            new=AsyncMock(side_effect=RuntimeError("queue unavailable")),
        ):
            with pytest.raises(RuntimeError):
                await ProductLifecycleService.reconcile(
                    product_ids=[1], now=started_at + timedelta(days=8)
                )

        async with db_session() as session:
            product = await session.get(Product, 1)
            assert product.is_active is True
            assert product.auto_hidden_at is None

        retried = await ProductLifecycleService.reconcile(
            product_ids=[1], now=started_at + timedelta(days=8)
        )
        assert retried["hidden"] == 1

    async def test_safe_sync_never_breaks_stock_update(
        self, db_session, seed_data, monkeypatch
    ):
        monkeypatch.setattr(settings, "product_lifecycle_enabled", True)
        with patch.object(
            ProductLifecycleService,
            "reconcile",
            new=AsyncMock(side_effect=RuntimeError("temporary failure")),
        ):
            result = await ProductLifecycleService.reconcile_safely_if_enabled(
                trigger="test", shop_id=1, product_ids=[1]
            )
        assert result == ProductLifecycleService.empty_result()
