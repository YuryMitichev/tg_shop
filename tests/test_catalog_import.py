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
# Сопоставление колонок
# ==========================

class TestColumnMatching:

    def test_match_name_ozon(self):
        assert _match_column("Название товара", "ozon") == "name"

    def test_match_name_wb(self):
        assert _match_column("Наименование", "wb") == "name"

    def test_match_name_ym(self):
        assert _match_column("Название", "ym") == "name"

    def test_match_description(self):
        assert _match_column("Описание", "ozon") == "description"
        assert _match_column("Описание товара", "wb") == "description"

    def test_keyword_fuzzy_match_name(self):
        assert _match_column("Полное название продукта", "ozon") == "name"
        assert _match_column("Коммерческое наименование", "wb") == "name"

    def test_unrecognized_column_returns_none(self):
        assert _match_column("Вес брутто", "ozon") is None
        assert _match_column("Ссылка на фото", "wb") is None
        assert _match_column("Цена продавца", "wb") is None


# ==========================
# Парсинг
# ==========================

class TestParseMarketplaceFile:

    def test_parse_ozon_file(self):
        data = _make_xlsx(
            ["Название товара", "Описание"],
            [
                ["Свеча «Лаванда»", "Натуральная соевая свеча"],
                ["Свеча «Мята»", "Свежий аромат"],
            ],
        )

        result = CatalogImportService.parse_marketplace_file(data, "ozon")

        assert result["source"] == "ozon"
        assert result["total_rows"] == 2
        assert result["recognized_rows"] == 2
        assert result["rows"][0]["name"] == "Свеча «Лаванда»"
        assert result["rows"][0]["description"] == "Натуральная соевая свеча"
        assert result["rows"][0]["recognized"] is True

    def test_parse_wb_file(self):
        data = _make_xlsx(
            ["Наименование", "Описание"],
            [
                ["Диффузор «Цитрус»", "Цитрусовый аромат"],
            ],
        )

        result = CatalogImportService.parse_marketplace_file(data, "wb")

        assert result["recognized_rows"] == 1
        assert result["rows"][0]["name"] == "Диффузор «Цитрус»"
        assert result["rows"][0]["description"] == "Цитрусовый аромат"

    def test_parse_wb_multirow_header(self):
        """Выгрузка WB: первая строка — названия групп колонок,
        вторая — реальные имена полей.
        Парсер должен найти строку заголовков и распознать данные."""
        wb = Workbook()
        ws = wb.active
        ws.append(["Основная информация", None, "Габариты", "Дополнительная информация"])
        ws.append(["Наименование", "Описание", "Вес брутто", "Ссылка на фото"])
        ws.append(["Свеча «Лаванда»", "Лавандовый аромат", 0.5, "https://..."])
        ws.append(["Диффузор «Цитрус»", "Цитрусовый аромат", 0.3, "https://..."])
        buf = BytesIO()
        wb.save(buf)
        data = buf.getvalue()

        result = CatalogImportService.parse_marketplace_file(data, "wb")

        assert result["recognized_rows"] == 2
        assert result["total_rows"] == 2
        assert result["rows"][0]["name"] == "Свеча «Лаванда»"
        assert result["rows"][0]["description"] == "Лавандовый аромат"
        assert result["rows"][1]["name"] == "Диффузор «Цитрус»"
        assert result["rows"][1]["description"] == "Цитрусовый аромат"

    def test_parse_ym_file(self):
        data = _make_xlsx(
            ["Название", "Описание"],
            [
                ["Набор свечей", "Подарочный набор"],
            ],
        )

        result = CatalogImportService.parse_marketplace_file(data, "ym")

        assert result["rows"][0]["name"] == "Набор свечей"
        assert result["rows"][0]["description"] == "Подарочный набор"

    def test_parse_without_description_column(self):
        """Если нет колонки описания — description пустой, строка всё равно распознана."""
        data = _make_xlsx(
            ["Название товара", "Вес брутто"],
            [["Товар", 0.5]],
        )

        result = CatalogImportService.parse_marketplace_file(data, "ozon")

        assert result["rows"][0]["name"] == "Товар"
        assert result["rows"][0]["description"] == ""
        assert result["rows"][0]["recognized"] is True

    def test_unrecognized_row_when_name_missing(self):
        data = _make_xlsx(
            ["Название", "Описание"],
            [
                [None, "Описание без названия"],
                ["Нормальный товар", "Описание"],
            ],
        )

        result = CatalogImportService.parse_marketplace_file(data, "ym")

        assert result["rows"][0]["recognized"] is False
        assert result["rows"][1]["recognized"] is True

    def test_skips_empty_rows(self):
        data = _make_xlsx(
            ["Название", "Описание"],
            [
                ["Товар 1", "Описание 1"],
                [None, None],
                ["Товар 2", "Описание 2"],
            ],
        )

        result = CatalogImportService.parse_marketplace_file(data, "ym")

        assert result["total_rows"] == 2


# ==========================
# Импорт в БД
# ==========================

class TestImportRows:

    async def test_import_creates_products(self, db_session, seed_data):
        rows = [
            {"name": "Свеча", "description": "Лаванда"},
            {"name": "Диффузор", "description": "Цитрус"},
        ]

        result = await CatalogImportService.import_rows(shop_id=1, rows=rows)

        assert result["created"] == 2

        from app.models.category import Category
        from app.models.product import Product
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
            assert prods[0].description == "Цитрус"
            assert prods[0].is_active is False

    async def test_import_uses_existing_category(self, db_session, seed_data):
        rows = [{"name": "Товар", "description": "Описание"}]

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
            ["Название", "Описание"],
            [["Тестовый товар", "Описание товара"]],
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
        assert data["rows"][0]["description"] == "Описание товара"

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
                        {"name": "Импорт-1", "description": ""},
                        {"name": "Импорт-2", "description": "Описание"},
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
