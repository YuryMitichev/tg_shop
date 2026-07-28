from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)

    products: Mapped[list["Product"]] = relationship(
        back_populates="category",
        order_by="Product.id",
    )
