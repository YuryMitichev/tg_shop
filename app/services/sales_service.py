from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_

from app.core.enums import OrderStatus
from app.models.order import Order


class SalesService:
    """Единое определение подтверждённой продажи для всех отчётов."""

    @staticmethod
    def confirmed_condition():
        return and_(
            Order.payment_confirmed_at.is_not(None),
            Order.status != OrderStatus.CANCELLED,
        )

    @staticmethod
    def confirm_order(
        order: Order,
        *,
        source: str,
        reference: str | None = None,
        confirmed_at: datetime | None = None,
    ) -> bool:
        """Идемпотентно фиксирует оплату; один Order всегда даёт одну продажу."""
        changed = False
        if order.payment_confirmed_at is None:
            order.payment_confirmed_at = confirmed_at or datetime.now()
            order.payment_confirmation_source = source
            order.payment_confirmation_ref = reference
            changed = True
        elif source == "online" and order.payment_confirmation_source != "online":
            # Успешный webhook является более сильным доказательством, чем ручная отметка.
            order.payment_confirmation_source = "online"
            order.payment_confirmation_ref = reference or order.payment_confirmation_ref
            changed = True
        return changed

    @staticmethod
    def invalidate_analytics() -> None:
        # Статус/оплата меняются редко; полная очистка трёх небольших TTL-кэшей
        # гарантирует, что менеджер сразу увидит подтверждённую продажу.
        from app.services.stats_service import StatsService

        StatsService._stats_cache.clear()
        StatsService._chart_cache.clear()
        StatsService._analytics_cache.clear()
