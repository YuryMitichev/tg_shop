from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        CheckConstraint("quantity BETWEEN 1 AND 100", name="ck_cart_items_quantity"),
        ForeignKeyConstraint(
            ["variant_id", "shop_id", "product_id"],
            ["product_variants.id", "product_variants.shop_id", "product_variants.product_id"],
            name="fk_cart_variant_tenant_product",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)

    telegram_user_id: Mapped[int] = mapped_column(index=True)

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))

    source_ref_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_source_refs.id", ondelete="SET NULL"), nullable=True
    )
    source_post_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_posts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    quantity: Mapped[int] = mapped_column(default=1)
