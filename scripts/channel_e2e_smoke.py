#!/usr/bin/env python3
"""Live Telegram -> polling -> OpenAI -> draft smoke test for a dedicated shop."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid

from aiogram import Bot
from sqlalchemy import delete, func, select

from app.database.db import async_session
from app.models.channel_import import (
    CatalogAnalysisRun,
    CatalogImportCandidate,
    CatalogImportJob,
    ChannelConnection,
    ChannelPost,
)
from app.services.channel_import_service import ChannelImportService
from app.services.shop_service import ShopService


WORKFLOW_VERSION = "channel-e2e-smoke-v1"


def _required_int(name: str) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        raise RuntimeError(f"{name} is required")
    return int(raw)


async def _wait_for_result(shop_id: int, message_id: int, timeout: int) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(ChannelPost, CatalogImportJob)
                    .join(CatalogImportJob, CatalogImportJob.post_id == ChannelPost.id)
                    .where(
                        ChannelPost.shop_id == shop_id,
                        ChannelPost.telegram_message_id == message_id,
                    )
                    .order_by(CatalogImportJob.id.desc())
                    .limit(1)
                )
            ).one_or_none()
            if row:
                post, job = row
                if job.status in {"completed", "failed", "needs_manual"}:
                    candidate_count = (
                        await session.execute(
                            select(func.count(CatalogImportCandidate.id)).where(
                                CatalogImportCandidate.job_id == job.id
                            )
                        )
                    ).scalar_one()
                    ai_run = (
                        await session.execute(
                            select(CatalogAnalysisRun).where(
                                CatalogAnalysisRun.job_id == job.id,
                                CatalogAnalysisRun.run_type == "cloud_ai",
                            )
                        )
                    ).scalar_one_or_none()
                    return {
                        "post_id": post.id,
                        "job_id": job.id,
                        "job_status": job.status,
                        "post_status": post.status,
                        "candidate_count": candidate_count,
                        "ai_run": ai_run is not None,
                        "ai_error": bool(ai_run and ai_run.error),
                    }
        await asyncio.sleep(2)
    raise TimeoutError(f"workflow did not finish in {timeout}s")


async def _cleanup(post_id: int) -> None:
    async with async_session() as session:
        await session.execute(delete(ChannelPost).where(ChannelPost.id == post_id))
        await session.commit()


async def run(timeout: int, keep_evidence: bool) -> dict:
    shop_id = _required_int("CHANNEL_SMOKE_SHOP_ID")
    channel_id = _required_int("CHANNEL_SMOKE_CHANNEL_ID")
    token = await ShopService.get_bot_token(shop_id)
    if not token:
        raise RuntimeError("dedicated smoke shop has no bot token")

    async with async_session() as session:
        connection = (
            await session.execute(
                select(ChannelConnection).where(ChannelConnection.shop_id == shop_id)
            )
        ).scalar_one_or_none()
        if not connection or connection.channel_id != channel_id or not connection.is_active:
            raise RuntimeError("smoke channel is not the active channel of the dedicated shop")

    correlation_id = uuid.uuid4().hex
    text = (
        f"SMOKE-{correlation_id} Тестовый товар: хлопковая футболка, "
        "размер M, цена 1000 ₽, в наличии 1 шт."
    )
    bot = Bot(token=token)
    message = None
    result: dict = {}
    started = time.monotonic()
    try:
        message = await bot.send_message(channel_id, text)
        result = await _wait_for_result(shop_id, message.message_id, timeout)
        if result["job_status"] != "completed":
            raise RuntimeError(f"terminal job status is {result['job_status']}")
        if not result["ai_run"] or result["ai_error"]:
            raise RuntimeError("cloud AI run is missing or failed")
        if result["candidate_count"] < 1:
            raise RuntimeError("AI did not create a product draft")

        duplicate_job_id = await ChannelImportService.ingest_post(
            shop_id,
            telegram_message_id=message.message_id,
            text=text,
            media=[],
        )
        if duplicate_job_id != result["job_id"]:
            raise RuntimeError("duplicate delivery created a second job")

        result.update(
            workflow_version=WORKFLOW_VERSION,
            correlation_id=correlation_id,
            outcome="success",
            duplicate_safe=True,
            latency_ms=round((time.monotonic() - started) * 1000),
        )
        return result
    finally:
        if message:
            try:
                await bot.delete_message(channel_id, message.message_id)
            except Exception:
                pass
        await bot.session.close()
        if result.get("post_id") and not keep_evidence:
            await _cleanup(result["post_id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--keep-evidence", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(run(args.timeout, args.keep_evidence)), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({
            "workflow_version": WORKFLOW_VERSION,
            "outcome": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
