"""legal_type column and shop_legal_documents table

Revision ID: a9b0c1d2e3f4
Revises: e8a9b0c1d2e3
Create Date: 2026-08-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9b0c1d2e3f4'
down_revision: Union[str, Sequence[str], None] = 'e8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shop_legal_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('document_type', sa.String(), nullable=False),
        sa.Column('seller_addendum', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shop_id', 'document_type', name='uq_shop_legal_documents_shop_type'),
    )
    op.create_index('ix_shop_legal_documents_shop_id', 'shop_legal_documents', ['shop_id'])
    op.create_index('ix_shop_legal_documents_document_type', 'shop_legal_documents', ['document_type'])

    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.add_column(sa.Column("legal_type", sa.String(), nullable=False, server_default="individual"))


def downgrade() -> None:
    with op.batch_alter_table("shops", schema=None) as batch_op:
        batch_op.drop_column("legal_type")

    op.drop_index('ix_shop_legal_documents_document_type', table_name='shop_legal_documents')
    op.drop_index('ix_shop_legal_documents_shop_id', table_name='shop_legal_documents')
    op.drop_table('shop_legal_documents')
