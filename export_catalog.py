"""
Экспорт каталога магазина из SQLite в JSON.

Использование на VPS:
    docker exec tg_shop_bot python export_catalog.py --shop "Linea_di_Luce"
    docker cp tg_shop_bot:/app/catalog_backup.json ./

Использование локально:
    python export_catalog.py --shop "Linea_di_Luce"
"""

import argparse
import asyncio
import json
import sys

from sqlalchemy import select

from app.database.db import async_session
from app.models.category import Category
from app.models.product import Product
from app.models.product_photo import ProductPhoto
from app.models.product_variant import ProductVariant
from app.models.shop import Shop


async def export_catalog(shop_name: str, output: str) -> None:
    async with async_session() as session:
        shop = await session.scalar(
            select(Shop).where(Shop.name == shop_name)
        )
        if shop is None:
            print(f"Магазин «{shop_name}» не найден в БД.")
            sys.exit(1)

        shop_id = shop.id
        print(f"Экспорт магазина: {shop.name} (id={shop_id})")

        result = await session.execute(
            select(Category)
            .where(Category.shop_id == shop_id)
            .order_by(Category.id)
        )
        categories = result.scalars().all()

        cat_list = []
        for cat in categories:
            cat_list.append({
                "id": cat.id,
                "name": cat.name,
                "emoji": cat.emoji,
            })

        result = await session.execute(
            select(Product)
            .where(Product.shop_id == shop_id)
            .order_by(Product.id)
        )
        products = result.scalars().all()

        prod_list = []
        for prod in products:
            result_v = await session.execute(
                select(ProductVariant)
                .where(ProductVariant.product_id == prod.id)
                .order_by(ProductVariant.id)
            )
            variants = result_v.scalars().all()

            result_p = await session.execute(
                select(ProductPhoto)
                .where(ProductPhoto.product_id == prod.id)
                .order_by(ProductPhoto.position)
            )
            photos = result_p.scalars().all()

            prod_list.append({
                "id": prod.id,
                "category_id": prod.category_id,
                "name": prod.name,
                "description": prod.description,
                "is_active": prod.is_active,
                "variants": [
                    {
                        "id": v.id,
                        "volume": v.volume,
                        "price": v.price,
                        "burn": v.burn,
                        "photo": v.photo,
                        "stock": v.stock,
                        "size": v.size,
                        "color": v.color,
                        "scent": v.scent,
                        "dimensions": v.dimensions,
                    }
                    for v in variants
                ],
                "photos": [
                    {
                        "id": p.id,
                        "file_id": p.file_id,
                        "position": p.position,
                    }
                    for p in photos
                ],
            })

        data = {
            "shop_name": shop.name,
            "shop_id": shop_id,
            "categories": cat_list,
            "products": prod_list,
        }

        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"Сохранено: {output}")
        print(f"  Категорий: {len(cat_list)}")
        print(f"  Товаров: {len(prod_list)}")
        total_variants = sum(len(p["variants"]) for p in prod_list)
        total_photos = sum(len(p["photos"]) for p in prod_list)
        print(f"  Вариантов: {total_variants}")
        print(f"  Фото: {total_photos}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Экспорт каталога в JSON")
    parser.add_argument("--shop", required=True, help="Название магазина")
    parser.add_argument("--out", default="catalog_backup.json", help="Выходной файл")
    args = parser.parse_args()

    asyncio.run(export_catalog(args.shop, args.out))
