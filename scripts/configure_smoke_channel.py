#!/usr/bin/env python3
"""Validate and connect the dedicated Telegram smoke channel."""

from __future__ import annotations

import asyncio
import json
import os

from aiogram import Bot
from aiogram.enums import ChatMemberStatus

from app.core.config import settings
from app.services.channel_import_service import ChannelImportService
from app.services.shop_service import ShopService


def _required_int(name: str) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return int(value)


async def configure() -> dict:
    shop_id = _required_int("CHANNEL_SMOKE_SHOP_ID")
    channel_id = _required_int("CHANNEL_SMOKE_CHANNEL_ID")
    shop = await ShopService.get(shop_id)
    token = await ShopService.get_bot_token(shop_id)
    if not shop or not token:
        raise RuntimeError("dedicated smoke shop or bot token is missing")

    sender_token = settings.platform_bot_token
    if not sender_token:
        raise RuntimeError("PLATFORM_BOT_TOKEN is required as an independent smoke sender")

    bot = Bot(token=token)
    sender_bot = Bot(token=sender_token)
    try:
        me = await bot.get_me()
        chat = await bot.get_chat(channel_id)
        member = await bot.get_chat_member(channel_id, me.id)
        if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
            raise RuntimeError("smoke bot is not a channel administrator")
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            if not getattr(member, "can_post_messages", False):
                raise RuntimeError("smoke bot cannot post messages")
            if not getattr(member, "can_delete_messages", False):
                raise RuntimeError("smoke bot cannot delete messages")

        sender = await sender_bot.get_me()
        print(json.dumps({
            "outcome": "validating_sender",
            "sender_bot_username": sender.username,
            "channel_id": channel_id,
        }, ensure_ascii=False), flush=True)
        try:
            sender_member = await sender_bot.get_chat_member(channel_id, sender.id)
        except Exception as exc:
            raise RuntimeError(
                f"platform bot @{sender.username} cannot access smoke channel: {exc}"
            ) from exc
        if sender_member.status not in {
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        }:
            raise RuntimeError("platform bot is not a smoke channel administrator")
        if sender_member.status == ChatMemberStatus.ADMINISTRATOR:
            if not getattr(sender_member, "can_post_messages", False):
                raise RuntimeError("platform bot cannot post smoke messages")
            if not getattr(sender_member, "can_delete_messages", False):
                raise RuntimeError("platform bot cannot delete smoke messages")

        connection = await ChannelImportService.connect_channel(
            shop_id,
            channel_id=channel_id,
            channel_title=chat.title or "Svoi Kanal Smoke Test",
            channel_username=chat.username,
            connected_by=shop["owner_telegram_id"],
        )
        return {
            "outcome": "configured",
            "shop_id": shop_id,
            "channel_id": channel_id,
            "connection_id": connection.id,
            "bot_username": me.username,
            "sender_bot_username": sender.username,
        }
    finally:
        await bot.session.close()
        await sender_bot.session.close()


def main() -> int:
    try:
        print(json.dumps(asyncio.run(configure()), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({
            "outcome": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
