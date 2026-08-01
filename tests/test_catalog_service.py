import pytest

from app.services.catalog_service import CatalogService


class TestCatalogService:

    async def test_get_categories(self, db_session, seed_data):
        categories = await CatalogService.get_categories(1)

        assert len(categories) == 2
        assert categories[0]["name"] == "Свечи"
        assert categories[1]["name"] == "Диффузоры"

    async def test_get_category(self, db_session, seed_data):
        category = await CatalogService.get_category(1, 1)

        assert category is not None
        assert category["name"] == "Свечи"

    async def test_get_category_not_found(self, db_session, seed_data):
        category = await CatalogService.get_category(1, 999)

        assert category is None

    async def test_get_products_only_active(self, db_session, seed_data):
        """Каталог показывает только видимые товары (is_active=True)."""
        products = await CatalogService.get_products(1, 1)

        assert len(products) == 1
        assert products[0]["name"] == "Кашемир"

    async def test_get_products_includes_variants(self, db_session, seed_data):
        products = await CatalogService.get_products(1, 1)

        assert len(products[0]["variants"]) == 2
        assert products[0]["variants"][0]["volume"] == "75 г"
        assert products[0]["variants"][0]["price"] == 450

    async def test_get_product(self, db_session, seed_data):
        product = await CatalogService.get_product(1, 1)

        assert product is not None
        assert product["name"] == "Кашемир"
        assert len(product["variants"]) == 2

    async def test_get_product_hidden(self, db_session, seed_data):
        """Скрытый товар не доступен покупателю."""
        product = await CatalogService.get_product(1, 2)

        assert product is None

    async def test_get_first_product(self, db_session, seed_data):
        product = await CatalogService.get_first_product(1, 1)

        assert product is not None
        assert product["id"] == 1

    async def test_get_first_product_empty_category(self, db_session, seed_data):
        product = await CatalogService.get_first_product(1, 999)

        assert product is None

    async def test_get_next_product_cyclic(self, db_session, seed_data):
        """Переход с последнего товара на первый (циклически)."""
        nxt = await CatalogService.get_next_product(1, 2, 3)

        assert nxt["id"] == 3

    async def test_get_previous_product_cyclic(self, db_session, seed_data):
        """Переход с первого товара на последний (циклически)."""
        prev = await CatalogService.get_previous_product(1, 2, 3)

        assert prev["id"] == 3

    async def test_get_variant(self, db_session, seed_data):
        product = await CatalogService.get_product(1, 1)

        variant = CatalogService.get_variant(product, 2)

        assert variant is not None
        assert variant["volume"] == "200 г"

    async def test_get_variant_not_found(self, db_session, seed_data):
        product = await CatalogService.get_product(1, 1)

        variant = CatalogService.get_variant(product, 999)

        assert variant is None

    async def test_get_first_variant(self, db_session, seed_data):
        product = await CatalogService.get_product(1, 1)

        variant = CatalogService.get_first_variant(product)

        assert variant["id"] == 1

    async def test_get_product_position(self, db_session, seed_data):
        position, total = await CatalogService.get_product_position(1, 1, 1)

        assert position == 1
        assert total == 1
