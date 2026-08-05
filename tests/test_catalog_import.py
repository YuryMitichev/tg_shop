"""Тесты импорта каталога из Ozon / Wildberries / Яндекс.Маркет."""
from io import BytesIO

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook

from app.api.main import create_app
from app.api.routes.admin import _read_upload_with_limit, MAX_IMPORT_FILE_SIZE, IMPORT_CHUNK_SIZE
from app.services.catalog_import_service import (
    CatalogImportService,
    _match_column,
    DEFAULT_CATEGORY_NAME,
)


def _make_xlsx(headers: list[str], rows: list[list]) -> bytes:
    """Создаёт .xlsx в памяти и возвращает байты."""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ==========================
# Парсинг
# ==========================

class TestColumnMatching:

    def test_match_ozon_columns(self):
        assert _match_column("Название товара", "ozon") == "name"
        assert _match_column("Цена, руб.", "ozon") == "price"
        assert _match_column("Остаток на складе", "ozon") == "stock"
        assert _match_column("Артикул", "ozon") == "sku"

    def test_match_wb_columns(self):
        assert _match_column("Наименование", "wb") == "name"
        assert _match_column("Цена продавца", "wb") == "price"
        assert _match_column("Количество", "wb") == "stock"
        assert _match_column("Артикул продавца", "wb") == "sku"

    def test_match_ym_columns(self):
        assert _match_column("Название", "ym") == "name"
        assert _match_column("Цена", "ym") == "price"
        assert _match_column("Остатки", "ym") == "stock"

    def test_keyword_fuzzy_match(self):
        assert _match_column("Полное название продукта", "ozon") == "name"
        assert _match_column("Цена с учётом скидки", "wb") == "price"
        assert _match_column("Доступный остаток", "ym") == "stock"

    def test_unrecognized_column_returns_none(self):
        assert _match_column("Вес брутто", "ozon") is None
        assert _match_column("Ссылка на фото", "wb") is None


class TestParseMarketplaceFile:

    def test_parse_ozon_file(self):
        data = _make_xlsx(
            ["Название товара", "Цена, руб.", "Остаток на складе", "Артикул"],
            [
                ["Свеча «Лаванда»", 450, 10, "SV-001"],
                ["Свеча «Мята»", 550, 5, "SV-002"],
            ],
        )

        result = CatalogImportService.parse_marketplace_file(data, "ozon")

        assert result["source"] == "ozon"
        assert result["total_rows"] == 2
        assert result["recognized_rows"] == 2
        assert result["rows"][0]["name"] == "Свеча «Лаванда»"
        assert result["rows"][0]["price"] == 450
        assert result["rows"][0]["stock"] == 10
        assert result["rows"][0]["recognized"] is True
        assert result["rows"][0]["warnings"] == []
        assert result["unmapped_columns"] == []

    def test_parse_wb_file(self):
        data = _make_xlsx(
            ["Наименование", "Цена продавца", "Количество"],
            [
                ["Диффузор «Цитрус»", 1290, 3],
            ],
        )

        result = CatalogImportService.parse_marketplace_file(data, "wb")

        assert result["recognized_rows"] == 1
        assert result["rows"][0]["name"] == "Диффузор «Цитрус»"
        assert result["rows"][0]["price"] == 1290
        assert result["rows"][0]["stock"] == 3

    def test_parse_ym_file(self):
        data = _make_xlsx(
            ["Название", "Цена", "Остатки"],
            [
                ["Набор свечей", 990, 7],
            ],
        )

        result = CatalogImportService.parse_marketplace_file(data, "ym")

        assert result["rows"][0]["name"] == "Набор свечей"
        assert result["rows"][0]["price"] == 990
        assert result["rows"][0]["stock"] == 7

    def test_price_as_float_string(self):
        data = _make_xlsx(
            ["Название", "Цена", "Остатки"],
            [["Товар", "1500.00", "2"]],
        )

        result = CatalogImportService.parse_marketplace_file(data, "ym")

        assert result["rows"][0]["price"] == 1500
        assert result["rows"][0]["stock"] == 2

    def test_unmapped_columns_collected(self):
        data = _make_xlsx(
            ["Название", "Цена", "Остатки", "Вес брутто", "Ссылка на фото"],
            [["Товар", 100, 1, 0.5, "https://..."]],
        )

        result = CatalogImportService.parse_marketplace_file(data, "ym")

        assert "Вес брутто" in result["unmapped_columns"]
        assert "Ссылка на фото" in result["unmapped_columns"]
        assert result["rows"][0]["recognized"] is True

    def test_unrecognized_row_when_name_missing(self):
        data = _make_xlsx(
            ["Название", "Цена", "Остатки"],
            [
                [None, 100, 5],
                ["Нормальный товар", 200, 3],
            ],
        )

        result = CatalogImportService.parse_marketplace_file(data, "ym")

        assert result["rows"][0]["recognized"] is False
        assert "Не распознано название товара" in result["rows"][0]["warnings"]
        assert result["rows"][1]["recognized"] is True

    def test_warning_when_stock_missing(self):
        data = _make_xlsx(
            ["Название", "Цена", "Остатки"],
            [["Товар", 100, None]],
        )

        result = CatalogImportService.parse_marketplace_file(data, "ym")

        assert result["rows"][0]["recognized"] is True
        assert "Не распознан остаток" in result["rows"][0]["warnings"]

    def test_skips_empty_rows(self):
        data = _make_xlsx(
            ["Название", "Цена", "Остатки"],
            [
                ["Товар 1", 100, 1],
                [None, None, None],
                ["Товар 2", 200, 2],
            ],
        )

        result = CatalogImportService.parse_marketplace_file(data, "ym")

        assert result["total_rows"] == 2


# ==========================
# Импорт в БД
# ==========================

class TestImportRows:

    async def test_import_creates_products_and_variants(self, db_session, seed_data):
        rows = [
            {"name": "Свеча", "price": 450, "stock": 10},
            {"name": "Диффузор", "price": 1290, "stock": 3},
        ]

        result = await CatalogImportService.import_rows(shop_id=1, rows=rows)

        assert result["created"] == 2

        from app.models.category import Category
        from app.models.product import Product
        from app.models.product_variant import ProductVariant
        from sqlalchemy import select

        async with db_session() as session:
            cats = await session.execute(
                select(Category).where(Category.name == DEFAULT_CATEGORY_NAME)
            )
            assert cats.scalars().first() is not None

            products = await session.execute(
                select(Product).where(Product.shop_id == 1).order_by(Product.id.desc())
            )
            prods = products.scalars().all()
            assert len(prods) >= 2
            assert prods[0].name == "Диффузор"
            assert prods[1].name == "Свеча"

            variants = await session.execute(
                select(ProductVariant).where(ProductVariant.shop_id == 1)
            )
            vars = variants.scalars().all()
            assert any(v.price == 450 and v.stock == 10 for v in vars)
            assert any(v.price == 1290 and v.stock == 3 for v in vars)

    async def test_import_uses_existing_category(self, db_session, seed_data):
        rows = [{"name": "Товар", "price": 100, "stock": 1}]

        result = await CatalogImportService.import_rows(
            shop_id=1, rows=rows, category_id=1
        )

        assert result["category_id"] == 1
        assert result["created"] == 1


# ==========================
# HTTP эндпоинты
# ==========================

class TestImportEndpoints:

    async def test_preview_endpoint(self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription):
        file_bytes = _make_xlsx(
            ["Название", "Цена", "Остатки"],
            [["Тестовый товар", 500, 5]],
        )

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/catalog/import/preview?source=ym",
                files={"file": ("test.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                cookies=admin_cookie,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 1
        assert data["rows"][0]["name"] == "Тестовый товар"
        assert data["rows"][0]["price"] == 500

    async def test_preview_invalid_source(self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/catalog/import/preview?source=amazon",
                files={"file": ("test.xlsx", b"fake", "application/octet-stream")},
                cookies=admin_cookie,
            )

        assert resp.status_code == 400

    async def test_preview_file_too_large(self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription):
        from app.api.routes.admin import MAX_IMPORT_FILE_SIZE

        oversized = b"x" * (MAX_IMPORT_FILE_SIZE + 1)

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/catalog/import/preview?source=ym",
                files={"file": ("big.xlsx", oversized, "application/octet-stream")},
                cookies=admin_cookie,
            )

        assert resp.status_code == 413

    async def test_confirm_endpoint(self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/catalog/import/confirm",
                json={
                    "rows": [
                        {"name": "Импорт-1", "price": 300, "stock": 2},
                        {"name": "Импорт-2", "price": 600, "stock": 4},
                    ],
                },
                cookies=admin_cookie,
            )

        assert resp.status_code == 200
        assert resp.json()["created"] == 2

    async def test_confirm_empty_rows_rejected(self, db_session, seed_data, admin_cookie, mock_admin_auth, active_subscription):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/catalog/import/confirm",
                json={"rows": []},
                cookies=admin_cookie,
            )

        assert resp.status_code == 400


# ==========================
# Потоковое чтение с лимитом
# ==========================

class _StreamingFakeFile:
    """Эмулирует UploadFile — генерирует данные на лету, без выделения всего объёма.

    Отслеживает bytes_consumed, чтобы тест мог убедиться,
    что функция не прочитала весь файл целиком.
    """

    def __init__(self, total_size: int, fill_byte: int = 0x41):
        self.total_size = total_size
        self.fill_byte = fill_byte
        self.bytes_consumed = 0

    async def read(self, size: int = -1) -> bytes:
        if self.bytes_consumed >= self.total_size:
            return b""
        remaining = self.total_size - self.bytes_consumed
        n = min(size, remaining) if size > 0 else remaining
        self.bytes_consumed += n
        return bytes([self.fill_byte]) * n


class TestStreamingSizeLimit:

    async def test_aborts_before_reading_entire_huge_file(self):
        """1 ГБ файл генерируется на лету — функция должна прерваться
        после ~MAX_IMPORT_FILE_SIZE, а не прочитать весь гигабайт."""
        ONE_GB = 1024 * 1024 * 1024
        fake = _StreamingFakeFile(total_size=ONE_GB)

        with pytest.raises(HTTPException) as exc_info:
            await _read_upload_with_limit(fake, MAX_IMPORT_FILE_SIZE)

        assert exc_info.value.status_code == 413

        assert fake.bytes_consumed <= MAX_IMPORT_FILE_SIZE + IMPORT_CHUNK_SIZE
        assert fake.bytes_consumed < ONE_GB // 50

    async def test_small_file_returned_intact(self):
        data = b"Hello, import!"
        fake = _StreamingFakeFile(total_size=len(data), fill_byte=0x48)

        result = await _read_upload_with_limit(fake, MAX_IMPORT_FILE_SIZE)

        assert len(result) == len(data)

    async def test_file_exactly_at_limit_passes(self):
        fake = _StreamingFakeFile(total_size=MAX_IMPORT_FILE_SIZE)

        result = await _read_upload_with_limit(fake, MAX_IMPORT_FILE_SIZE)

        assert len(result) == MAX_IMPORT_FILE_SIZE
