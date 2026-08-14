"""payment idempotency

Revision ID: k3d4e5f6a7b8
Revises: j1a2b3c4d5e6
Create Date: 2026-08-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'j1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('shop_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('provider_payment_id', sa.String(length=255), nullable=True),
    sa.Column('idempotency_key', sa.String(length=255), nullable=False),
    sa.Column('amount_minor', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key', name='uq_payments_idempotency_key'),
    sa.UniqueConstraint('order_id', 'attempt', name='uq_payments_order_attempt')
    )
    op.create_index(op.f('ix_payments_order_id'), 'payments', ['order_id'], unique=False)
    op.create_index(op.f('ix_payments_shop_id'), 'payments', ['shop_id'], unique=False)
    op.create_index(op.f('ix_payments_provider_payment_id'), 'payments', ['provider_payment_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_payments_provider_payment_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_shop_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_order_id'), table_name='payments')
    op.drop_table('payments')
