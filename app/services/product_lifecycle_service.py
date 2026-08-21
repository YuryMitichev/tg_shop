import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.database.db import async_session
from app.models.product import Product
from app.services.channel_post_button_service import ChannelPostButtonService


logger = logging.getLogger(__name__)


class ProductLifecycleService:
    """Управляет устойчивым жизненным циклом товаров без остатка."""

    WORKFLOW_VERSION = "product-lifecycle-v1"
    HIDE_AFTER = timedelta(days=7)
    DELETE_AFTER = timedelta(days=30)

    @staticmethod
    def has_stock(product: Product) -> bool:
        return any(variant.stock > 0 for variant in product.variants)

    @staticmethod
    async def reconcile_if_enabled(
        *,
        shop_id: int | None = None,
        product_ids: list[int] | set[int] | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        if not settings.product_lifecycle_enabled:
            return ProductLifecycleService.empty_result()
        return await ProductLifecycleService.reconcile(
            shop_id=shop_id,
            product_ids=product_ids,
            now=now,
        )

    @staticmethod
    async def reconcile_safely_if_enabled(
        *,
        trigger: str,
        shop_id: int | None = None,
        product_ids: list[int] | set[int] | None = None,
    ) -> dict[str, int]:
        try:
            return await ProductLifecycleService.reconcile_if_enabled(
                shop_id=shop_id,
                product_ids=product_ids,
            )
        except Exception:
            logger.exception(
                "Product lifecycle version=%s trigger=%s outcome=failed",
                ProductLifecycleService.WORKFLOW_VERSION,
                trigger,
            )
            return ProductLifecycleService.empty_result()

    @staticmethod
    def empty_result() -> dict[str, int]:
        return {
            "scanned": 0,
            "started": 0,
            "hidden": 0,
            "deleted": 0,
            "restored": 0,
        }

    @staticmethod
    async def reconcile(
        *,
        shop_id: int | None = None,
        product_ids: list[int] | set[int] | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        current_time = now or datetime.now()
        result = ProductLifecycleService.empty_result()

        query = (
            select(Product)
            .options(selectinload(Product.variants))
            .where(Product.lifecycle_deleted_at.is_(None))
            .order_by(Product.id)
            .with_for_update(skip_locked=True)
        )
        if shop_id is not None:
            query = query.where(Product.shop_id == shop_id)
        if product_ids is not None:
            ids = list(set(product_ids))
            if not ids:
                return result
            query = query.where(Product.id.in_(ids))

        async with async_session() as session:
            products = list((await session.execute(query)).scalars().all())
            result["scanned"] = len(products)

            for product in products:
                if ProductLifecycleService.has_stock(product):
                    if product.out_of_stock_since is not None:
                        product.out_of_stock_since = None
                    if product.auto_hidden_at is not None:
                        product.auto_hidden_at = None
                        product.is_active = True
                        result["restored"] += 1
                        await ChannelPostButtonService.enqueue_product_change_in_session(
                            session,
                            product.shop_id,
                            product.id,
                            reason="product_restocked",
                        )
                    continue

                if product.out_of_stock_since is None:
                    product.out_of_stock_since = current_time
                    result["started"] += 1

                elapsed = current_time - product.out_of_stock_since
                if elapsed >= ProductLifecycleService.DELETE_AFTER:
                    product.is_active = False
                    product.lifecycle_deleted_at = current_time
                    result["deleted"] += 1
                    await ChannelPostButtonService.enqueue_product_change_in_session(
                        session,
                        product.shop_id,
                        product.id,
                        reason="product_lifecycle_deleted",
                    )
                elif (
                    elapsed >= ProductLifecycleService.HIDE_AFTER
                    and product.is_active
                ):
                    product.is_active = False
                    product.auto_hidden_at = current_time
                    result["hidden"] += 1
                    await ChannelPostButtonService.enqueue_product_change_in_session(
                        session,
                        product.shop_id,
                        product.id,
                        reason="product_out_of_stock_hidden",
                    )

            await session.commit()

        return result

    @staticmethod
    def changed(result: dict[str, int]) -> bool:
        return any(result[key] for key in ("started", "hidden", "deleted", "restored"))

    @staticmethod
    def log_result(result: dict[str, int], *, trigger: str) -> None:
        logger.info(
            "Product lifecycle version=%s trigger=%s scanned=%d started=%d "
            "hidden=%d deleted=%d restored=%d outcome=completed",
            ProductLifecycleService.WORKFLOW_VERSION,
            trigger,
            result["scanned"],
            result["started"],
            result["hidden"],
            result["deleted"],
            result["restored"],
        )
