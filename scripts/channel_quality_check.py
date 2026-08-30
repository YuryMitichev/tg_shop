#!/usr/bin/env python3
"""Return a non-zero status when reviewed AI drafts need quality attention."""

from __future__ import annotations

import asyncio
import json
import os

from sqlalchemy import func, select

from app.database.db import async_session
from app.models.channel_import import CatalogImportCandidate


async def collect() -> dict:
    min_reviews = int(os.getenv("CHANNEL_QUALITY_MIN_REVIEWS", "20"))
    max_rate = float(os.getenv("CHANNEL_QUALITY_MAX_CORRECTION_RATE", "40"))
    async with async_session() as session:
        reviewed, corrected = (
            await session.execute(
                select(
                    func.count(CatalogImportCandidate.id),
                    func.count(CatalogImportCandidate.id).filter(
                        CatalogImportCandidate.correction_count > 0
                    ),
                ).where(CatalogImportCandidate.reviewed_at.is_not(None))
            )
        ).one()
    rate = round((corrected / reviewed * 100) if reviewed else 0, 1)
    return {
        "reviewed": reviewed,
        "corrected": corrected,
        "correction_rate_percent": rate,
        "threshold_percent": max_rate,
        "alert": reviewed >= min_reviews and rate > max_rate,
    }


def main() -> int:
    result = asyncio.run(collect())
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["alert"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
