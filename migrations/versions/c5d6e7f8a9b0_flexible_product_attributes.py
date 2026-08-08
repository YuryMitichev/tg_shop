"""flexible product attributes

Revision ID: c5d6e7f8a9b0
Revises: b3c4d5e6f7a8
Create Date: 2026-08-06 12:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LABEL_MAP = {
    "volume": "Объём",
    "burn": "Время горения",
    "size": "Размер",
    "color": "Цвет",
    "scent": "Аромат",
    "dimensions": "Длина/Ширина/Высота",
}


def upgrade() -> None:
    op.create_table(
        "product_attribute_defs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("shop_id", "key", name="uq_product_attr_defs_shop_key"),
    )
    op.create_index("ix_product_attribute_defs_shop_id", "product_attribute_defs", ["shop_id"])

    op.add_column(
        "product_variants",
        sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    op.execute("""
        UPDATE product_variants
        SET attributes = COALESCE(
            json_strip_nulls(json_build_object(
                'burn', burn,
                'size', size,
                'color', color,
                'scent', scent,
                'dimensions', dimensions
            )),
            '{}'::json
        )
    """)

    with op.batch_alter_table("product_variants") as batch_op:
        batch_op.drop_column("burn")
        batch_op.drop_column("size")
        batch_op.drop_column("color")
        batch_op.drop_column("scent")
        batch_op.drop_column("dimensions")

    conn = op.get_bind()
    shops = conn.execute(sa.text("SELECT id, product_attrs FROM shops")).fetchall()

    for shop_id, product_attrs_json in shops:
        attrs = json.loads(product_attrs_json) if product_attrs_json else ["volume"]

        seed_keys = ["burn"]
        for a in attrs:
            if a not in seed_keys and a != "volume":
                seed_keys.append(a)

        for position, key in enumerate(seed_keys):
            label = _LABEL_MAP.get(key, key)
            conn.execute(sa.text(
                "INSERT INTO product_attribute_defs (shop_id, key, label, position, is_required) "
                "VALUES (:shop_id, :key, :label, :position, false)"
            ), {"shop_id": shop_id, "key": key, "label": label, "position": position})

    op.drop_column("shops", "product_attrs")


def downgrade() -> None:
    op.add_column(
        "shops",
        sa.Column("product_attrs", sa.String(), server_default='["volume"]'),
    )

    with op.batch_alter_table("product_variants") as batch_op:
        batch_op.add_column(sa.Column("burn", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("size", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("color", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("scent", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("dimensions", sa.String(), nullable=True))

    op.execute("""
        UPDATE product_variants SET
            burn = attributes->>'burn',
            size = attributes->>'size',
            color = attributes->>'color',
            scent = attributes->>'scent',
            dimensions = attributes->>'dimensions'
    """)

    op.drop_column("product_variants", "attributes")
    op.drop_index("ix_product_attribute_defs_shop_id", table_name="product_attribute_defs")
    op.drop_table("product_attribute_defs")
