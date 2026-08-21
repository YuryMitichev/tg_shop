"""security hardening: tenant integrity, reservations, roles and token hashes

Revision ID: r0e1f2a3b4c5
Revises: q9d0e1f2a3b4
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa


revision = "r0e1f2a3b4c5"
down_revision = "q9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("role", sa.String(length=16), server_default="manager", nullable=False),
    )
    op.execute(
        """
        UPDATE admin_users AS admin
        SET role = 'owner'
        FROM shops
        WHERE shops.id = admin.shop_id
          AND shops.owner_telegram_id = admin.telegram_user_id
        """
    )
    op.execute(
        """
        INSERT INTO admin_users (
            shop_id, telegram_user_id, display_name, role, created_at
        )
        SELECT id, owner_telegram_id, 'Владелец', 'owner', CURRENT_TIMESTAMP
        FROM shops
        ON CONFLICT (shop_id, telegram_user_id)
        DO UPDATE SET role = 'owner'
        """
    )
    op.create_check_constraint(
        "ck_admin_users_role",
        "admin_users",
        "role IN ('owner', 'manager', 'content', 'support')",
    )

    op.add_column("login_tokens", sa.Column("token_hash", sa.String(length=64), nullable=True))
    op.execute(
        "UPDATE login_tokens "
        "SET token_hash = encode(sha256(convert_to(token, 'UTF8')), 'hex')"
    )
    op.alter_column("login_tokens", "token_hash", nullable=False)
    op.create_index(
        "ix_login_tokens_token_hash", "login_tokens", ["token_hash"], unique=True
    )
    op.drop_index("ix_login_tokens_token", table_name="login_tokens")
    op.drop_constraint("uq_login_tokens_token", "login_tokens", type_="unique")
    op.drop_column("login_tokens", "token")

    op.add_column("orders", sa.Column("stock_reserved_until", sa.DateTime(), nullable=True))
    op.add_column("orders", sa.Column("stock_released_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_orders_stock_reserved_until",
        "orders",
        ["stock_reserved_until"],
        unique=False,
    )
    op.execute(
        """
        UPDATE orders
        SET stock_reserved_until = CURRENT_TIMESTAMP + INTERVAL '20 minutes'
        WHERE status IN ('new', 'confirmed')
          AND payment_confirmed_at IS NULL
        """
    )

    # Quarantine impossible historical financial rows before enforcing checks.
    op.execute(
        "UPDATE orders SET status = 'cancelled', total_amount = 1 "
        "WHERE total_amount <= 0"
    )
    op.execute(
        "UPDATE orders SET payment_method = 'manual' "
        "WHERE payment_method NOT IN ('manual', 'yookassa') OR payment_method IS NULL"
    )
    op.create_check_constraint("ck_orders_positive_total", "orders", "total_amount > 0")
    op.create_check_constraint(
        "ck_orders_payment_method",
        "orders",
        "payment_method IN ('manual', 'yookassa')",
    )

    op.execute("UPDATE product_variants SET stock = 0 WHERE stock < 0")
    op.create_check_constraint(
        "ck_product_variants_nonnegative_stock", "product_variants", "stock >= 0"
    )
    op.create_unique_constraint("uq_products_id_shop", "products", ["id", "shop_id"])
    op.execute(
        """
        UPDATE product_variants AS variant
        SET shop_id = product.shop_id
        FROM products AS product
        WHERE product.id = variant.product_id
          AND variant.shop_id <> product.shop_id
        """
    )
    op.create_unique_constraint(
        "uq_variants_id_shop_product",
        "product_variants",
        ["id", "shop_id", "product_id"],
    )
    op.create_foreign_key(
        "fk_variants_product_tenant",
        "product_variants",
        "products",
        ["product_id", "shop_id"],
        ["id", "shop_id"],
        ondelete="CASCADE",
    )

    op.execute("DELETE FROM cart_items WHERE quantity <= 0")
    op.execute("UPDATE cart_items SET quantity = 100 WHERE quantity > 100")
    op.execute(
        """
        DELETE FROM cart_items AS cart
        WHERE NOT EXISTS (
            SELECT 1
            FROM product_variants AS variant
            JOIN products AS product
              ON product.id = variant.product_id
             AND product.shop_id = variant.shop_id
            WHERE variant.id = cart.variant_id
              AND variant.shop_id = cart.shop_id
              AND variant.product_id = cart.product_id
        )
        """
    )
    op.create_check_constraint(
        "ck_cart_items_quantity", "cart_items", "quantity BETWEEN 1 AND 100"
    )
    op.create_foreign_key(
        "fk_cart_variant_tenant_product",
        "cart_items",
        "product_variants",
        ["variant_id", "shop_id", "product_id"],
        ["id", "shop_id", "product_id"],
        ondelete="CASCADE",
    )

    op.execute("UPDATE order_items SET quantity = 1 WHERE quantity <= 0")
    op.create_check_constraint(
        "ck_order_items_positive_quantity", "order_items", "quantity > 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_order_items_positive_quantity", "order_items", type_="check")
    op.drop_constraint(
        "fk_cart_variant_tenant_product", "cart_items", type_="foreignkey"
    )
    op.drop_constraint("ck_cart_items_quantity", "cart_items", type_="check")
    op.drop_constraint("fk_variants_product_tenant", "product_variants", type_="foreignkey")
    op.drop_constraint(
        "uq_variants_id_shop_product", "product_variants", type_="unique"
    )
    op.drop_constraint("uq_products_id_shop", "products", type_="unique")
    op.drop_constraint(
        "ck_product_variants_nonnegative_stock", "product_variants", type_="check"
    )
    op.drop_constraint("ck_orders_payment_method", "orders", type_="check")
    op.drop_constraint("ck_orders_positive_total", "orders", type_="check")
    op.drop_index("ix_orders_stock_reserved_until", table_name="orders")
    op.drop_column("orders", "stock_released_at")
    op.drop_column("orders", "stock_reserved_until")

    op.add_column("login_tokens", sa.Column("token", sa.String(), nullable=True))
    op.execute("UPDATE login_tokens SET token = token_hash")
    op.alter_column("login_tokens", "token", nullable=False)
    op.create_unique_constraint("uq_login_tokens_token", "login_tokens", ["token"])
    op.create_index("ix_login_tokens_token", "login_tokens", ["token"], unique=True)
    op.drop_index("ix_login_tokens_token_hash", table_name="login_tokens")
    op.drop_column("login_tokens", "token_hash")

    op.drop_constraint("ck_admin_users_role", "admin_users", type_="check")
    op.drop_column("admin_users", "role")
