"""add legal_type and shop_legal_documents

Revision ID: g8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'g8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.add_column(sa.Column("legal_type", sa.String(), nullable=False, server_default="individual"))

    op.create_table(
        "shop_legal_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(), nullable=False),
        sa.Column("seller_addendum", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("shop_id", "document_type", name="uq_shop_legal_documents_shop_type"),
    )
    op.create_index("ix_shop_legal_documents_shop_id", "shop_legal_documents", ["shop_id"])
    op.create_index("ix_shop_legal_documents_document_type", "shop_legal_documents", ["document_type"])


def downgrade() -> None:
    op.drop_index("ix_shop_legal_documents_document_type", table_name="shop_legal_documents")
    op.drop_index("ix_shop_legal_documents_shop_id", table_name="shop_legal_documents")
    op.drop_table("shop_legal_documents")

    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.drop_column("legal_type")
