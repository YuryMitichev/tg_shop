from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from app.api.auth import get_current_user, get_optional_user
from app.api.main import create_app
from app.models.product_variant import ProductVariant


async def test_public_catalog_marks_active_zero_stock_product(
    db_session, seed_data
):
    async with db_session() as session:
        await session.execute(
            update(ProductVariant)
            .where(ProductVariant.product_id == 1)
            .values(stock=0)
        )
        await session.commit()

    app = create_app()

    async def current_user():
        return {"id": 777, "shop_id": 1}

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_optional_user] = current_user

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/shop/products?category_id=1",
            headers={"X-Shop-Id": "1"},
        )

    assert response.status_code == 200
    product = next(item for item in response.json() if item["id"] == 1)
    assert product["is_out_of_stock"] is True
