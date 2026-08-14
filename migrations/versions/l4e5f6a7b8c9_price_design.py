"""price design settings

Revision ID: l4e5f6a7b8c9
Revises: k3d4e5f6a7b8
Create Date: 2026-08-14 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'l4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'k3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.add_column(sa.Column("theme_price_color", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("theme_price_size", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("theme_price_weight", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.drop_column("theme_price_weight")
        batch_op.drop_column("theme_price_size")
        batch_op.drop_column("theme_price_color")
