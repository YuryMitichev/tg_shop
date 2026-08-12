"""per-shop theme customization

Revision ID: j1a2b3c4d5e6
Revises: h9c0d1e2f3a4
Create Date: 2026-08-12 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'j1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'h9c0d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.add_column(sa.Column("theme_primary_color", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("theme_bg_color", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("theme_text_color", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("theme_button_text_color", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("theme_secondary_bg_color", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("theme_radius", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("theme_font_family", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.drop_column("theme_font_family")
        batch_op.drop_column("theme_radius")
        batch_op.drop_column("theme_secondary_bg_color")
        batch_op.drop_column("theme_button_text_color")
        batch_op.drop_column("theme_text_color")
        batch_op.drop_column("theme_bg_color")
        batch_op.drop_column("theme_primary_color")
