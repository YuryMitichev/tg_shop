"""set canonical subscription pricing

Revision ID: w5j6k7l8m9n0
Revises: v4i5j6k7l8m9
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa


revision = "w5j6k7l8m9n0"
down_revision = "v4i5j6k7l8m9"
branch_labels = None
depends_on = None


plans = sa.table(
    "subscription_plans",
    sa.column("id", sa.Integer()),
    sa.column("name", sa.String()),
    sa.column("description", sa.Text()),
    sa.column("price", sa.Float()),
    sa.column("duration_days", sa.Integer()),
    sa.column("is_trial", sa.Boolean()),
    sa.column("is_active", sa.Boolean()),
    sa.column("features", sa.Text()),
)


def _upsert_plan(bind, *, name, description, price, duration_days, is_trial):
    query = sa.select(plans.c.id).where(plans.c.name == name).limit(1)
    plan_id = bind.execute(query).scalar_one_or_none()

    if plan_id is None and is_trial:
        plan_id = bind.execute(
            sa.select(plans.c.id)
            .where(plans.c.is_trial.is_(True))
            .order_by(plans.c.id)
            .limit(1)
        ).scalar_one_or_none()

    values = {
        "name": name,
        "description": description,
        "price": price,
        "duration_days": duration_days,
        "is_trial": is_trial,
        "is_active": True,
    }
    if plan_id is None:
        bind.execute(plans.insert().values(**values))
    else:
        bind.execute(plans.update().where(plans.c.id == plan_id).values(**values))
    return plan_id


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(plans.update().values(is_active=False))

    _upsert_plan(
        bind,
        name="Пробный период — 14 дней",
        description="Бесплатный пробный период — все возможности",
        price=0,
        duration_days=14,
        is_trial=True,
    )
    _upsert_plan(
        bind,
        name="Подписка — 1 месяц",
        description="Полный функционал магазина за 1 299 ₽ в месяц.",
        price=1299,
        duration_days=30,
        is_trial=False,
    )
    _upsert_plan(
        bind,
        name="Подписка — 3 месяца",
        description="Оплата за 3 месяца со скидкой 10%: 3 507,30 ₽ вместо 3 897 ₽.",
        price=3507.30,
        duration_days=90,
        is_trial=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(plans.update().values(is_active=False))

    _upsert_plan(
        bind,
        name="Триал 7 дней",
        description="Бесплатный пробный период — все возможности",
        price=0,
        duration_days=7,
        is_trial=True,
    )
    _upsert_plan(
        bind,
        name="Подписка — 1 месяц",
        description="Полный функционал магазина. Стоимость: 5000₽/мес.",
        price=5000,
        duration_days=30,
        is_trial=False,
    )
    _upsert_plan(
        bind,
        name="Подписка — 6 месяцев",
        description="Полный функционал магазина. Выгода 3000₽ (скидка 10%).",
        price=27000,
        duration_days=180,
        is_trial=False,
    )
    _upsert_plan(
        bind,
        name="Подписка — 12 месяцев",
        description="Полный функционал магазина. Выгода 12000₽ (скидка 20%).",
        price=48000,
        duration_days=365,
        is_trial=False,
    )
