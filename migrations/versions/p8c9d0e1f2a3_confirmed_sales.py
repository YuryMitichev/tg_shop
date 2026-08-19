"""confirmed sales source of truth

Revision ID: p8c9d0e1f2a3
Revises: o7b8c9d0e1f2
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa


revision = "p8c9d0e1f2a3"
down_revision = "o7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_confirmed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "orders", sa.Column("payment_confirmation_source", sa.String(), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("payment_confirmation_ref", sa.String(), nullable=True)
    )
    op.create_index(
        "ix_orders_payment_confirmed_at", "orders", ["payment_confirmed_at"]
    )

    # Сначала восстанавливаем подтверждения из успешных платежей.
    op.execute(
        """
        UPDATE orders AS o
        SET payment_confirmed_at = COALESCE(
                (SELECT MIN(COALESCE(p.updated_at, p.created_at))
                 FROM payments AS p
                 WHERE p.order_id = o.id AND p.status = 'succeeded'),
                o.status_updated_at,
                o.created_at
            ),
            payment_confirmation_source = 'online',
            payment_confirmation_ref = COALESCE(
                (SELECT p.provider_payment_id
                 FROM payments AS p
                 WHERE p.order_id = o.id AND p.status = 'succeeded'
                 ORDER BY p.id
                 LIMIT 1),
                o.payment_id
            )
        WHERE EXISTS (
            SELECT 1 FROM payments AS p
            WHERE p.order_id = o.id AND p.status = 'succeeded'
        )
        """
    )

    # Для старых заказов, созданных до появления платежного аудита,
    # сохраняем уже подтверждённый менеджером/legacy-провайдером факт.
    op.execute(
        """
        UPDATE orders
        SET payment_confirmed_at = COALESCE(status_updated_at, created_at),
            payment_confirmation_source = CASE
                WHEN payment_method = 'manual' THEN 'manual'
                ELSE 'legacy_status'
            END,
            payment_confirmation_ref = payment_id
        WHERE payment_confirmed_at IS NULL
          AND status IN ('paid', 'shipped', 'done')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_orders_payment_confirmed_at", table_name="orders")
    op.drop_column("orders", "payment_confirmation_ref")
    op.drop_column("orders", "payment_confirmation_source")
    op.drop_column("orders", "payment_confirmed_at")
