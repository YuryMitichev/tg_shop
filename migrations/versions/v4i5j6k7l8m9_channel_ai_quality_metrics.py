"""channel AI quality metrics

Revision ID: v4i5j6k7l8m9
Revises: u3h4c5d6e7f8
"""

from alembic import op
import sqlalchemy as sa


revision = "v4i5j6k7l8m9"
down_revision = "u3h4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_import_candidates",
        sa.Column("correction_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "catalog_import_candidates",
        sa.Column("corrected_fields", sa.JSON(), server_default="[]", nullable=False),
    )
    op.add_column(
        "catalog_import_candidates",
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "catalog_import_candidates",
        sa.Column("review_outcome", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("catalog_import_candidates", "review_outcome")
    op.drop_column("catalog_import_candidates", "reviewed_at")
    op.drop_column("catalog_import_candidates", "corrected_fields")
    op.drop_column("catalog_import_candidates", "correction_count")
