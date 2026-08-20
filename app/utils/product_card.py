from app.services.catalog_service import CatalogService
from app.services.review_service import ReviewService
from app.utils.escape import esc


class ProductCard:

    @staticmethod
    async def render(product: dict, variant_id: int | None = None):

        if variant_id is None:
            variant = CatalogService.get_first_variant(product)
        else:
            variant = CatalogService.get_variant(product, variant_id)

        if variant is None:
            variant = CatalogService.get_first_variant(product)

        lines = []

        lines.append(f"<b>{esc(product['name'])}</b>")
        lines.append("")

        summary = await ReviewService.get_rating_summary(product["id"])
        if summary:
            stars = "⭐" * round(summary["avg"])
            lines.append(f"{stars} {summary['avg']} ({summary['count']} отз.)")
            lines.append("")

        lines.append(esc(product["description"]))
        lines.append("")
        lines.append(f"💰 <b>{variant['price']} ₽</b>")

        if variant.get("attributes", {}).get("burn"):
            lines.append(f"🔥 До {esc(variant['attributes']['burn'])}")

        return "\n".join(lines)
