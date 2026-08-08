from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    price: Mapped[float] = mapped_column(Float, default=0)

    duration_days: Mapped[int] = mapped_column(Integer, default=30)

    is_trial: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    features: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)

    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), nullable=False)

    plan_id: Mapped[int] = mapped_column(ForeignKey("subscription_plans.id"), nullable=False)

    # trial | active | expired | cancelled
    status: Mapped[str] = mapped_column(String(20), default="trial")

    started_at: Mapped[datetime] = mapped_column(server_default=func.now())

    expires_at: Mapped[datetime] = mapped_column(nullable=False)

    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Для платных подписок — ID платежа во внешней системе
    external_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
