"""CRUD-сервис для определений характеристик товаров (product_attribute_defs)."""

import re

from sqlalchemy import select

from app.database.db import async_session
from app.models.product_attribute_def import ProductAttributeDef


def _slugify(label: str) -> str:
    """Превращает человекочитаемое название в machine key.

    «Время горения» → «vremya_goreniya»,
    «Цвет» → «cvet».
    """
    s = label.strip().lower()
    translit = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
        "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
        "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
        "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya",
    }
    s = "".join(translit.get(c, c) for c in s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "attr"


class ProductAttrService:
    """Управление определениями характеристик товаров для магазина."""

    @staticmethod
    async def list_defs(shop_id: int) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(ProductAttributeDef)
                .where(ProductAttributeDef.shop_id == shop_id)
                .order_by(ProductAttributeDef.position, ProductAttributeDef.id)
            )
            return [_def_to_dict(d) for d in result.scalars().all()]

    @staticmethod
    async def create_def(shop_id: int, label: str, key: str | None = None) -> dict:
        slug = key or _slugify(label)

        async with async_session() as session:
            existing = await session.execute(
                select(ProductAttributeDef)
                .where(
                    ProductAttributeDef.shop_id == shop_id,
                    ProductAttributeDef.key == slug,
                )
            )
            if existing.scalar_one_or_none():
                count_result = await session.execute(
                    select(ProductAttributeDef)
                    .where(ProductAttributeDef.shop_id == shop_id)
                )
                count = len(count_result.scalars().all())
                slug = f"{slug}_{count + 1}"

            max_pos_result = await session.execute(
                select(ProductAttributeDef)
                .where(ProductAttributeDef.shop_id == shop_id)
                .order_by(ProductAttributeDef.position.desc())
                .limit(1)
            )
            last = max_pos_result.scalar_one_or_none()
            next_pos = (last.position + 1) if last else 0

            attr_def = ProductAttributeDef(
                shop_id=shop_id,
                key=slug,
                label=label.strip(),
                position=next_pos,
            )
            session.add(attr_def)
            await session.commit()
            await session.refresh(attr_def)
            return _def_to_dict(attr_def)

    @staticmethod
    async def update_def(
        shop_id: int,
        attr_id: int,
        label: str | None = None,
        position: int | None = None,
    ) -> dict | None:
        async with async_session() as session:
            result = await session.execute(
                select(ProductAttributeDef).where(
                    ProductAttributeDef.shop_id == shop_id,
                    ProductAttributeDef.id == attr_id,
                )
            )
            attr_def = result.scalar_one_or_none()
            if not attr_def:
                return None

            if label is not None:
                attr_def.label = label.strip()
            if position is not None:
                attr_def.position = position

            await session.commit()
            await session.refresh(attr_def)
            return _def_to_dict(attr_def)

    @staticmethod
    async def delete_def(shop_id: int, attr_id: int) -> bool:
        async with async_session() as session:
            result = await session.execute(
                select(ProductAttributeDef).where(
                    ProductAttributeDef.shop_id == shop_id,
                    ProductAttributeDef.id == attr_id,
                )
            )
            attr_def = result.scalar_one_or_none()
            if not attr_def:
                return False
            await session.delete(attr_def)
            await session.commit()
            return True


def _def_to_dict(d: ProductAttributeDef) -> dict:
    return {
        "id": d.id,
        "key": d.key,
        "label": d.label,
        "position": d.position,
        "is_required": d.is_required,
    }
