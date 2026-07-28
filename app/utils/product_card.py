from app.services.catalog_service import CatalogService


class ProductCard:

    @staticmethod
    def render(product: dict, variant_id: int | None = None):

        if variant_id is None:
            variant = CatalogService.get_first_variant(product)
        else:
            variant = CatalogService.get_variant(product, variant_id)

        if variant is None:
            variant = CatalogService.get_first_variant(product)

        lines = []

        lines.append(f"<b>{product['name']}</b>")
        lines.append("")
        lines.append(product["description"])
        lines.append("")
        lines.append(f"💰 <b>{variant['price']} ₽</b>")

        if variant["burn"]:
            lines.append(f"🔥 До {variant['burn']}")

        return "\n".join(lines)
