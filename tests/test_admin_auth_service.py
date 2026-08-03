import time
from unittest.mock import AsyncMock, patch

import jwt

from app.core.config import settings
from app.services.admin_auth_service import AdminAuthService


class TestMagicLinkAuth:
    """Тесты авторизации через magic link."""

    def setup_method(self):
        AdminAuthService._tokens.clear()

    async def test_verify_login_token_valid(self):
        token = "test-valid-token-abc123"
        AdminAuthService._tokens[token] = (
            123456,
            time.time() + 300,
            1,
            False,
        )

        jwt_token = AdminAuthService.verify_login_token(token)

        assert jwt_token is not None

        payload = jwt.decode(
            jwt_token,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
        assert payload["sub"] == "123456"
        assert payload["shop_id"] == 1
        assert payload["super_admin"] is False

    def test_verify_login_token_expired(self):
        token = "test-expired-token"
        AdminAuthService._tokens[token] = (
            123456,
            time.time() - 10,
            1,
            False,
        )

        result = AdminAuthService.verify_login_token(token)
        assert result is None
        assert token not in AdminAuthService._tokens

    def test_verify_login_token_wrong(self):
        result = AdminAuthService.verify_login_token("nonexistent-token")
        assert result is None

    def test_verify_login_token_single_use(self):
        token = "test-single-use-token"
        AdminAuthService._tokens[token] = (
            123456,
            time.time() + 300,
            1,
            True,
        )

        jwt1 = AdminAuthService.verify_login_token(token)
        assert jwt1 is not None

        jwt2 = AdminAuthService.verify_login_token(token)
        assert jwt2 is None

    def test_verify_login_token_super_admin_flag(self):
        token = "test-super-admin-token"
        AdminAuthService._tokens[token] = (
            999,
            time.time() + 300,
            1,
            True,
        )

        jwt_token = AdminAuthService.verify_login_token(token)
        payload = jwt.decode(
            jwt_token,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
        assert payload["super_admin"] is True

    async def test_request_login_unknown_user(self):
        with patch.object(
            AdminAuthService, "_resolve_shop_id", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = None

            result = await AdminAuthService.request_login(999999)

            assert result is False

    async def test_request_login_success(self):
        with patch.object(
            AdminAuthService, "_resolve_shop_id", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = (1, False)

            with patch("app.services.admin_auth_service.get_bot") as mock_get_bot:
                mock_bot = AsyncMock()
                mock_get_bot.return_value = mock_bot

                result = await AdminAuthService.request_login(123456)

                assert result is True
                mock_bot.send_message.assert_called_once()

                sent_text = mock_bot.send_message.call_args[0][1]
                assert "login?token=" in sent_text

    async def test_request_login_bot_unavailable(self):
        with patch.object(
            AdminAuthService, "_resolve_shop_id", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = (1, False)

            with patch("app.services.admin_auth_service.get_bot") as mock_get_bot:
                mock_get_bot.return_value = None

                result = await AdminAuthService.request_login(123456)
                assert result is False

    async def test_request_login_generates_long_token(self):
        with patch.object(
            AdminAuthService, "_resolve_shop_id", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = (1, False)

            with patch("app.services.admin_auth_service.get_bot") as mock_get_bot:
                mock_bot = AsyncMock()
                mock_get_bot.return_value = mock_bot

                await AdminAuthService.request_login(123456)

                assert len(AdminAuthService._tokens) == 1
                token = list(AdminAuthService._tokens.keys())[0]
                assert len(token) >= 50
