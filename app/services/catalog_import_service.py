"""Импорт каталога из выгрузок маркетплейсов (Ozon / Wildberries / Яндекс.Маркет).

Парсит .xlsx-файлы и извлекает только название и описание товара.
Цену, остаток, характеристики и фото пользователь добавляет вручную
после импорта.
"""
from io import BytesIO
from typing import Any, Literal

from openpyxl import load_workbook
from sqlalchemy import select

from app.database.db import async_session
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant

MarketplaceSource = Literal["ozon", "wb", "ym"]

DEFAULT_CATEGORY_NAME = "Импортировано"

# Точные alias'ы названий колонок для каждого источника.
_COLUMN_ALIASES: dict[str, dict[str, list[str]]] = {
    "ozon": {
        "name": ["Название товара", "Название", "Product name", "Наименование"],
        "description": ["Описание", "Description", "Описание товара"],
        "category": ["Категория", "Категория товара", "Категория продавца", "Item category"],
    },
    "wb": {
        "name": ["Наименование", "Название", "Коммерческое наименование"],
        "description": ["Описание", "Описание товара", "Composition", "Состав"],
        "category": ["Категория", "Категория продавца", "Предмет", "Категория товара"],
    },
    "ym": {
        "name": ["Название", "Наименование товара", "name", "Название товара"],
        "description": ["Описание", "Описание товара", "description"],
        "category": ["Категория", "Категория продавца", "category", "Категория товара"],
    },
}

# Keyword-матчинг: если точный alias не найден, ищем подстроку (case-insensitive).
_COLUMN_KEYWORDS: dict[str, list[str]] = {
    "name": ["назван", "наименован", "product name", "коммерческое наименован"],
    "description": ["описан", "description"],
    "category": ["категори", "предмет"],
}

_MATCHED_FIELDS = list(_COLUMN_KEYWORDS.keys())

# Сколько первых строк проверять в поисках строки заголовков.
# Выгрузки WB имеют двухуровневый заголовок (группы колонок → имена полей),
# поэтому простого чтения первой строки недостаточно.
HEADER_SCAN_ROWS = 5

PREVIEW_ROW_LIMIT = 500


def _match_column(header: str, source: MarketplaceSource) -> str | None:
    """Сопоставляет заголовок колонки с полем (name/description).

    Сначала точное совпадение по alias, потом keyword-подстрока.
    Возвращает имя поля или None.
    """
    header_norm = header.strip().lower()

    for field in _MATCHED_FIELDS:
        for alias in _COLUMN_ALIASES[source].get(field, []):
            if header.strip() == alias:
                return field

    for field, keywords in _COLUMN_KEYWORDS.items():
        for kw in keywords:
            if kw in header_norm:
                return field

    return None


class CatalogImportService:
    """Парсинг и импорт каталога из выгрузок маркетплейсов."""

    @staticmethod
    def parse_marketplace_file(file_bytes: bytes, source: MarketplaceSource) -> dict:
        """Парсит .xlsx файл и возвращает превью без записи в БД.

        Извлекает только название и описание.
        Строка считается распознанной, если найдено название.

        Возвращает dict:
            source, total_rows, recognized_rows,
            rows: [{row_number, name, description, recognized}],
            unmapped_columns: [str]
        """
        wb = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb.active

        candidate_rows = list(
            ws.iter_rows(min_row=1, max_row=HEADER_SCAN_ROWS, values_only=True)
        )
        if not candidate_rows:
            wb.close()
            return {
                "source": source,
                "total_rows": 0,
                "recognized_rows": 0,
                "rows": [],
                "unmapped_columns": [],
            }

        best_header_idx = 0
        best_match_count = -1
        column_map: dict[str, int] = {}
        raw_headers: list[str] = []

        for idx, cand_row in enumerate(candidate_rows):
            cand_headers = [
                str(c).strip() if c is not None else "" for c in cand_row
            ]
            cand_map: dict[str, int] = {}
            for col_idx, header in enumerate(cand_headers):
                if not header:
                    continue
                field = _match_column(header, source)
                if field and field not in cand_map:
                    cand_map[field] = col_idx
            if len(cand_map) > best_match_count:
                best_match_count = len(cand_map)
                best_header_idx = idx
                column_map = cand_map
                raw_headers = cand_headers

        header_row_num = best_header_idx + 1  # 1-based

        name_idx = column_map.get("name")
        desc_idx = column_map.get("description")
        cat_idx = column_map.get("category")

        rows: list[dict] = []
        truncated = False

        for row_num, row in enumerate(
            ws.iter_rows(min_row=header_row_num + 1, values_only=True),
            start=header_row_num + 1,
        ):
            if row is None or all(c is None or str(c).strip() == "" for c in row):
                continue

            name = str(row[name_idx]).strip() if name_idx is not None and name_idx < len(row) and row[name_idx] else ""

            description = ""
            if desc_idx is not None and desc_idx < len(row) and row[desc_idx]:
                description = str(row[desc_idx]).strip()

            category = ""
            if cat_idx is not None and cat_idx < len(row) and row[cat_idx]:
                category = str(row[cat_idx]).strip()

            recognized = bool(name)

            rows.append({
                "row_number": row_num,
                "name": name,
                "description": description,
                "category": category,
                "recognized": recognized,
            })

            if len(rows) >= PREVIEW_ROW_LIMIT:
                truncated = True
                break

        wb.close()

        recognized_count = sum(1 for r in rows if r["recognized"])

        return {
            "source": source,
            "total_rows": len(rows),
            "recognized_rows": recognized_count,
            "rows": rows,
            "unmapped_columns": [],
            "truncated": truncated,
        }

    @staticmethod
    async def import_rows(
        shop_id: int,
        rows: list[dict],
        category_id: int | None = None,
    ) -> dict:
        """Создаёт Product + плейсхолдер ProductVariant для каждой строки.

        Товары создаются скрытыми (is_active=False) — пользователь
        заполнит цену, характеристики и фото вручную перед публикацией.

        Если в строке есть поле category — создаётся или находится
        категория с этим именем. Иначе используется category_id или
        категория «Импортировано».

        Возвращает {created, category_id, categories}.
        """
        async with async_session() as session:
            category_cache: dict[str, int] = {}

            async def _get_category_id(name: str) -> int:
                if name in category_cache:
                    return category_cache[name]
                result = await session.execute(
                    select(Category).where(
                        Category.shop_id == shop_id,
                        Category.name == name,
                    )
                )
                cat = result.scalar_one_or_none()
                if cat is None:
                    cat = Category(shop_id=shop_id, name=name)
                    session.add(cat)
                    await session.flush()
                category_cache[name] = cat.id
                return cat.id

            if category_id is None:
                result = await session.execute(
                    select(Category).where(
                        Category.shop_id == shop_id,
                        Category.name == DEFAULT_CATEGORY_NAME,
                    )
                )
                category = result.scalar_one_or_none()
                if category is None:
                    category = Category(shop_id=shop_id, name=DEFAULT_CATEGORY_NAME)
                    session.add(category)
                    await session.flush()
                category_id = category.id

            created = 0
            for row in rows:
                row_category_name = row.get("category", "").strip()
                if row_category_name:
                    row_cat_id = await _get_category_id(row_category_name)
                else:
                    row_cat_id = category_id

                product = Product(
                    shop_id=shop_id,
                    category_id=row_cat_id,
                    name=row["name"],
                    description=row.get("description") or "",
                    is_active=False,
                )
                product.variants = [
                    ProductVariant(
                        shop_id=shop_id,
                        volume="Стандарт",
                        price=0,
                        stock=0,
                        attributes={},
                    )
                ]
                session.add(product)
                created += 1

            await session.commit()

            return {"created": created, "category_id": category_id}
