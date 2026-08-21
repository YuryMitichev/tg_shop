from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database.db import Base


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint(
            "id", "shop_id", "product_id", name="uq_variants_id_shop_product"
        ),
        CheckConstraint("stock >= 0", name="ck_product_variants_nonnegative_stock"),
        ForeignKeyConstraint(
            ["product_id", "shop_id"],
            ["products.id", "products.shop_id"],
            name="fk_variants_product_tenant",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), index=True, default=1)
    # The tenant-aware composite FK below is the only ORM path to Product.
    # Keeping a second scalar FK here makes SQLAlchemy relationships ambiguous.
    product_id: Mapped[int] = mapped_column()

    volume: Mapped[str] = mapped_column(nullable=False)
    price: Mapped[int] = mapped_column(nullable=False)
    photo: Mapped[str | None] = mapped_column(nullable=True)
    stock: Mapped[int] = mapped_column(default=0, nullable=False)

    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    product: Mapped["Product"] = relationship(
        back_populates="variants",
        foreign_keys=[product_id, shop_id],
    )
