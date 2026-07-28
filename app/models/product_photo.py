from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class ProductPhoto(Base):
    __tablename__ = "product_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))

    file_id: Mapped[str] = mapped_column(nullable=False)
    position: Mapped[int] = mapped_column(default=0)

    product: Mapped["Product"] = relationship(back_populates="photos")
