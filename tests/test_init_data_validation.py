import hashlib
import hmac
import json
import logging
import time
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

from app.api.auth import get_current_user, validate_init_data
from app.core.config import settings

BOT_TOKEN = "7000000001:test-bot-token-fixture"
USER = {"id": 424242, "first_name": "Тестовый Юзер", "username": "test_user"}


def build_init_data(
    auth_date: int | str | None,
    user: dict | None = USER,
    extra: dict | None = None,
    sign_with: str = BOT_TOKEN,
) -> str:
    """Собирает валидно подписанный initData с заданным auth_date."""
    params = {
        "query_id": "AAF-test-query-id",
        "user": json.dumps(user, ensure_ascii=False),
    }
    if auth_date is not None:
        params["auth_date"] = str(auth_date)
    if extra:
        params.update(extra)

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", sign_with.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(params)


@pytest.fixture(autouse=True)
def pin_settings(monkeypatch):
    monkeypatch.setattr(settings, "init_data_max_age", 300)
    monkeypatch.setattr(settings, "init_data_clock_skew", 30)


class TestValidateInitDataAuthDate:
    async def test_valid_current_auth_date_accepted(self):
        init_data = build_init_data(auth_date=int(time.time()))
        result = await validate_init_data(init_data, BOT_TOKEN)
        assert result is not None
        assert result["id"] == USER["id"]
        assert result["first_name"] == USER["first_name"]

    async def test_recent_auth_date_within_max_age_accepted(self):
        init_data = build_init_data(auth_date=int(time.time()) - 60)
        assert await validate_init_data(init_data, BOT_TOKEN) is not None

    async def test_expired_auth_date_rejected(self):
        age = 300 + 30 + 60
        init_data = build_init_data(auth_date=int(time.time()) - age)
        assert await validate_init_data(init_data, BOT_TOKEN) is None

    async def test_just_beyond_max_age_plus_skew_rejected(self):
        age = 300 + 30 + 2
        init_data = build_init_data(auth_date=int(time.time()) - age)
        assert await validate_init_data(init_data, BOT_TOKEN) is None

    async def test_future_auth_date_beyond_skew_rejected(self):
        init_data = build_init_data(auth_date=int(time.time()) + 30 + 600)
        assert await validate_init_data(init_data, BOT_TOKEN) is None

    async def test_future_auth_date_within_skew_accepted(self):
        init_data = build_init_data(auth_date=int(time.time()) + 10)
        assert await validate_init_data(init_data, BOT_TOKEN) is not None

    async def test_missing_auth_date_rejected(self):
        init_data = build_init_data(auth_date=None)
        assert await validate_init_data(init_data, BOT_TOKEN) is None

    @pytest.mark.parametrize(
        "bad_value",
        ["", "abc", "12.5", "-1", "+123", " 123", "1_0", "1e9", "١٧", "12у1"],
    )
    async def test_malformed_auth_date_rejected(self, bad_value):
        init_data = build_init_data(auth_date=bad_value)
        assert await validate_init_data(init_data, BOT_TOKEN) is None

    async def test_invalid_signature_rejected(self):
        init_data = build_init_data(auth_date=int(time.time()), sign_with="1:wrong-token")
        assert await validate_init_data(init_data, BOT_TOKEN) is None

    async def test_tampered_user_rejected(self):
        init_data = build_init_data(auth_date=int(time.time()))
        params_part, hash_part = init_data.rsplit("&hash=", 1)
        forged = params_part + "&hash=" + "0" * len(hash_part)
        assert await validate_init_data(forged, BOT_TOKEN) is None

    async def test_empty_init_data_rejected(self):
        assert await validate_init_data("", BOT_TOKEN) is None

    async def test_init_data_without_hash_rejected(self):
        init_data = build_init_data(auth_date=int(time.time()))
        assert await validate_init_data(init_data.split("&hash=")[0], BOT_TOKEN) is None

    async def test_configurable_max_age(self, monkeypatch):
        monkeypatch.setattr(settings, "init_data_max_age", 3600)
        init_data = build_init_data(auth_date=int(time.time()) - 1800)
        assert await validate_init_data(init_data, BOT_TOKEN) is not None
        monkeypatch.setattr(settings, "init_data_max_age", 300)
        assert await validate_init_data(init_data, BOT_TOKEN) is None


class TestInitDataNotLogged:
    async def test_rejected_init_data_not_logged(self, caplog):
        init_data = build_init_data(
            auth_date=int(time.time()), sign_with="1:wrong-token"
        )
        with caplog.at_level(logging.WARNING, logger="app.api.auth"):
            assert await validate_init_data(init_data, BOT_TOKEN) is None

        for record in caplog.records:
            message = record.getMessage()
            assert init_data not in message
            assert "hash=" not in message
            assert USER["first_name"] not in message
            assert USER["username"] not in message

    async def test_get_current_user_failure_log_has_no_init_data(self, caplog):
        init_data = build_init_data(auth_date=int(time.time()) - 10_000)
        with patch(
            "app.api.auth.ShopService.get_bot_token",
            new=AsyncMock(return_value=BOT_TOKEN),
        ):
            with caplog.at_level(logging.WARNING, logger="app.api.auth"):
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(
                        authorization=f"tma {init_data}", x_shop_id=1
                    )

        assert exc_info.value.status_code == 401
        for record in caplog.records:
            message = record.getMessage()
            assert init_data not in message
            assert "hash=" not in message
            assert USER["first_name"] not in message
