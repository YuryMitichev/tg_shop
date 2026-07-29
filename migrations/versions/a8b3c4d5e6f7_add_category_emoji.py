"""add category emoji

Revision ID: a8b3c4d5e6f7
Revises: 70708932a1e0
Create Date: 2026-07-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a8b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = '70708932a1e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляет колонку emoji и разделяет существующие имена."""
    op.add_column('categories', sa.Column('emoji', sa.String(), nullable=True))

    op.execute("""
        UPDATE categories
        SET emoji = substr(name, 1, instr(name, ' ') - 1),
            name = trim(substr(name, instr(name, ' ') + 1))
        WHERE instr(name, ' ') > 0
          AND unicode(substr(name, 1, 1)) > 127
    """)


def downgrade() -> None:
    """Объединяет emoji обратно в name и удаляет колонку."""
    op.execute("""
        UPDATE categories
        SET name = emoji || ' ' || name
        WHERE emoji IS NOT NULL AND emoji != ''
    """)

    op.drop_column('categories', 'emoji')
