"""
Импорт каталога из JSON в БД (PostgreSQL).

Использование после наката схемы и создания магазина:
    python import_catalog.py --file catalog_backup.json --shop-id 1

ID категорий/товаров/вариантов не сохраняются — создаются новые.
Photo file_id переносятся (они валидны пока существует бот).
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


async def import_catalog(file_path: str, shop_id: int) -> None:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Импорт из {file_path} → shop_id={shop_id}")
    print(f"  Магазин-источник: {data['shop_name']}")

    async with async_session() as session:
        for cat_data in data["categories"]:
            existing = await session.scalar(
                select(Category)
                .where(Category.shop_id == shop_id, Category.name == cat_data["name"])
            )
            if existing:
                print(f"  Категория «{cat_data['name']}» уже существует — пропуск")
                old_cat_id = cat_data["id"]
                cat_data["_new_id"] = existing.id
                continue

            cat = Category(
                shop_id=shop_id,
                name=cat_data["name"],
                emoji=cat_data.get("emoji"),
            )
            session.add(cat)
            await session.flush()
            cat_data["_new_id"] = cat.id
            print(f"  + Категория: {cat.name} (id={cat.id})")

        for prod_data in data["products"]:
            old_cat_id = prod_data["category_id"]
            new_cat_id = None
            for cat_data in data["categories"]:
                if cat_data["id"] == old_cat_id:
                    new_cat_id = cat_data["_new_id"]
                    break

            if new_cat_id is None:
                print(f"  ! Товар «{prod_data['name']}»: категория {old_cat_id} не найдена — пропуск")
                continue

            existing = await session.scalar(
                select(Product)
                .where(
                    Product.shop_id == shop_id,
                    Product.name == prod_data["name"],
                    Product.category_id == new_cat_id,
                )
            )
            if existing:
                print(f"  Товар «{prod_data['name']}» уже существует — пропуск")
                continue

            product = Product(
                shop_id=shop_id,
                category_id=new_cat_id,
                name=prod_data["name"],
                description=prod_data["description"],
                is_active=prod_data["is_active"],
            )
            session.add(product)
            await session.flush()
            print(f"  + Товар: {product.name} (id={product.id})")

            for v_data in prod_data.get("variants", []):
                variant = ProductVariant(
                    shop_id=shop_id,
                    product_id=product.id,
                    volume=v_data["volume"],
                    price=v_data["price"],
                    burn=v_data.get("burn"),
                    photo=v_data.get("photo"),
                    stock=v_data.get("stock", 0),
                    size=v_data.get("size"),
                    color=v_data.get("color"),
                    scent=v_data.get("scent"),
                    dimensions=v_data.get("dimensions"),
                )
                session.add(variant)

            for p_data in prod_data.get("photos", []):
                photo = ProductPhoto(
                    shop_id=shop_id,
                    product_id=product.id,
                    file_id=p_data["file_id"],
                    position=p_data["position"],
                )
                session.add(photo)

        await session.commit()

    print("Готово.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Импорт каталога из JSON")
    parser.add_argument("--file", required=True, help="JSON файл")
    parser.add_argument("--shop-id", type=int, required=True, help="ID магазина в новой БД")
    args = parser.parse_args()

    asyncio.run(import_catalog(args.file, args.shop_id))
