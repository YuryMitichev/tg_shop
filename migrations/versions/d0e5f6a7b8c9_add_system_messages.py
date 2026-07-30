"""add system_messages table

Revision ID: d0e5f6a7b8c9
Revises: c9d4e5f6a7b8
Create Date: 2026-07-29 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd0e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c9d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('system_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )


def downgrade() -> None:
    op.drop_table('system_messages')
