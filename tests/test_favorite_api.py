from httpx import ASGITransport, AsyncClient

from app.api.auth import get_current_user, get_optional_user
from app.api.main import create_app


def _favorite_app(user_id: int = 777):
    app = create_app()

    async def current_user():
        return {"id": user_id, "shop_id": 1}

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_optional_user] = current_user
    return app


class TestFavoriteApi:
    async def test_add_list_catalog_detail_and_remove(self, db_session, seed_data):
        app = _favorite_app()
        transport = ASGITransport(app=app)
        headers = {"X-Shop-Id": "1"}

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            added = await client.put("/api/shop/favorites/1", headers=headers)
            assert added.status_code == 200
            assert added.json() == {"product_id": 1, "is_favorite": True}

            favorites = await client.get("/api/shop/favorites", headers=headers)
            assert favorites.status_code == 200
            assert [item["id"] for item in favorites.json()] == [1]
            assert favorites.json()[0]["is_favorite"] is True

            catalog = await client.get(
                "/api/shop/products?category_id=1", headers=headers
            )
            assert catalog.status_code == 200
            assert catalog.json()[0]["is_favorite"] is True

            detail = await client.get("/api/shop/products/1", headers=headers)
            assert detail.status_code == 200
            assert detail.json()["is_favorite"] is True

            removed = await client.delete("/api/shop/favorites/1", headers=headers)
            assert removed.status_code == 200
            assert removed.json()["is_favorite"] is False

            empty = await client.get("/api/shop/favorites", headers=headers)
            assert empty.json() == []

    async def test_add_is_idempotent_and_users_are_isolated(
        self, db_session, seed_data
    ):
        headers = {"X-Shop-Id": "1"}
        first_app = _favorite_app(111)
        async with AsyncClient(
            transport=ASGITransport(app=first_app), base_url="http://test"
        ) as client:
            first = await client.put("/api/shop/favorites/1", headers=headers)
            second = await client.put("/api/shop/favorites/1", headers=headers)
            assert first.status_code == 200
            assert second.status_code == 200

        second_app = _favorite_app(222)
        async with AsyncClient(
            transport=ASGITransport(app=second_app), base_url="http://test"
        ) as client:
            response = await client.get("/api/shop/favorites", headers=headers)
            assert response.status_code == 200
            assert response.json() == []

    async def test_inactive_product_is_rejected(self, db_session, seed_data):
        app = _favorite_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put(
                "/api/shop/favorites/2", headers={"X-Shop-Id": "1"}
            )
        assert response.status_code == 404
