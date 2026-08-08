from datetime import datetime

from sqlalchemy import UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


LEGAL_DOCUMENT_TYPES = [
    "privacy_policy",
    "customer_consent",
    "order_terms",
    "data_processing_mandate",
]


class ShopLegalDocument(Base):
    """Пер-магазин правовой документ.

    Каждый тип документа имеет защищённый системный шаблон
    (генерируется кодом, не редактируется продавцом) и необязательное
    дополнение продавца (seller_addendum).
    """

    __tablename__ = "shop_legal_documents"
    __table_args__ = (
        UniqueConstraint("shop_id", "document_type", name="uq_shop_legal_documents_shop_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    shop_id: Mapped[int] = mapped_column(index=True)

    document_type: Mapped[str] = mapped_column(index=True)

    seller_addendum: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
