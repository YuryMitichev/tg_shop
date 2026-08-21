import time
from datetime import datetime, timedelta, timezone
import hashlib
from unittest.mock import AsyncMock, patch

import jwt
import pytest

from app.core.config import settings
from app.models.login_token import LoginToken
from app.services.admin_auth_service import AdminAuthService


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TestMagicLinkAuth:
    """Тесты авторизации через magic link."""

    async def test_verify_login_token_valid(self, db_session, seed_data):
        token = "test-valid-token-abc123-0123456789abcdef"
        async with db_session() as session:
            session.add(LoginToken(
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                telegram_user_id=123456,
                shop_id=1,
                is_super_admin=False,
                expires_at=_utcnow() + timedelta(seconds=300),
            ))
            await session.commit()

        jwt_token = await AdminAuthService.verify_login_token(token)

        assert jwt_token is not None

        payload = jwt.decode(
            jwt_token,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
        assert payload["sub"] == "123456"
        assert payload["shop_id"] == 1
        assert payload["super_admin"] is False

    async def test_verify_login_token_expired(self, db_session, seed_data):
        token = "test-expired-token-0123456789abcdef"
        async with db_session() as session:
            session.add(LoginToken(
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                telegram_user_id=123456,
                shop_id=1,
                is_super_admin=False,
                expires_at=_utcnow() - timedelta(seconds=10),
            ))
            await session.commit()

        result = await AdminAuthService.verify_login_token(token)
        assert result is None

    async def test_verify_login_token_wrong(self, db_session, seed_data):
        result = await AdminAuthService.verify_login_token("nonexistent-token")
        assert result is None

    async def test_verify_login_token_single_use(self, db_session, seed_data):
        token = "test-single-use-token-0123456789abcdef"
        async with db_session() as session:
            session.add(LoginToken(
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                telegram_user_id=123456,
                shop_id=1,
                is_super_admin=True,
                expires_at=_utcnow() + timedelta(seconds=300),
            ))
            await session.commit()

        jwt1 = await AdminAuthService.verify_login_token(token)
        assert jwt1 is not None

        jwt2 = await AdminAuthService.verify_login_token(token)
        assert jwt2 is None

    async def test_verify_login_token_super_admin_flag(self, db_session, seed_data):
        token = "test-super-admin-token-0123456789abcdef"
        async with db_session() as session:
            session.add(LoginToken(
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                telegram_user_id=999,
                shop_id=1,
                is_super_admin=True,
                expires_at=_utcnow() + timedelta(seconds=300),
            ))
            await session.commit()

        jwt_token = await AdminAuthService.verify_login_token(token)
        payload = jwt.decode(
            jwt_token,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
        assert payload["super_admin"] is True

    async def test_request_login_unknown_user(self):
        with patch.object(
            AdminAuthService, "_resolve_shop_ids", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = []

            result = await AdminAuthService.request_login(999999)

            assert result is False

    async def test_request_login_success(self, db_session, seed_data):
        with patch.object(
            AdminAuthService, "_resolve_shop_ids", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = [(1, False)]

            with patch("app.services.admin_auth_service.get_bot") as mock_get_bot:
                mock_bot = AsyncMock()
                mock_get_bot.return_value = mock_bot

                result = await AdminAuthService.request_login(123456)

                assert result is True
                mock_bot.send_message.assert_called_once()

                sent_text = mock_bot.send_message.call_args[0][1]
                assert "login#token=" in sent_text

    async def test_request_login_multiple_shops(self, db_session, seed_data):
        with patch.object(
            AdminAuthService, "_resolve_shop_ids", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = [(2, False), (1, False)]

            with patch("app.services.admin_auth_service.get_bot") as mock_get_bot:
                mock_bot_a = AsyncMock()
                mock_bot_b = AsyncMock()
                mock_get_bot.side_effect = [mock_bot_a, mock_bot_b]

                result = await AdminAuthService.request_login(123456)

                assert result is True
                assert mock_bot_a.send_message.call_count == 1
                assert mock_bot_b.send_message.call_count == 1

    async def test_request_login_bot_unavailable(self, db_session, seed_data):
        with patch.object(
            AdminAuthService, "_resolve_shop_ids", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = [(1, False)]

            with patch("app.services.admin_auth_service.get_bot") as mock_get_bot:
                mock_get_bot.return_value = None

                result = await AdminAuthService.request_login(123456)
                assert result is False

    async def test_request_login_generates_long_token(self, db_session, seed_data):
        with patch.object(
            AdminAuthService, "_resolve_shop_ids", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = [(1, False)]

            with patch("app.services.admin_auth_service.get_bot") as mock_get_bot:
                mock_bot = AsyncMock()
                mock_get_bot.return_value = mock_bot

                await AdminAuthService.request_login(123456)

            async with db_session() as session:
                from sqlalchemy import select
                result = await session.execute(select(LoginToken))
                tokens = result.scalars().all()
                assert len(tokens) == 1
                assert len(tokens[0].token_hash) == 64

    async def test_request_login_cleans_expired(self, db_session, seed_data):
        async with db_session() as session:
            session.add(LoginToken(
                token_hash=hashlib.sha256(b"old-expired").hexdigest(),
                telegram_user_id=111,
                shop_id=1,
                is_super_admin=False,
                expires_at=_utcnow() - timedelta(hours=1),
            ))
            await session.commit()

        with patch.object(
            AdminAuthService, "_resolve_shop_ids", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = [(1, False)]

            with patch("app.services.admin_auth_service.get_bot") as mock_get_bot:
                mock_bot = AsyncMock()
                mock_get_bot.return_value = mock_bot

                await AdminAuthService.request_login(123456)

        async with db_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(LoginToken).where(
                    LoginToken.token_hash
                    == hashlib.sha256(b"old-expired").hexdigest()
                )
            )
            assert result.scalar_one_or_none() is None
