import hashlib

from app.services.tinkoff_client import _generate_token, verify_token


class TestTinkoffToken:

    def test_generate_token_basic(self):
        params = {
            "TerminalKey": "test_terminal",
            "Amount": 100000,
            "OrderId": "1",
        }
        password = "test_password"

        token = _generate_token(params, password)

        expected_data = {
            "TerminalKey": "test_terminal",
            "Amount": 100000,
            "OrderId": "1",
            "Password": "test_password",
        }
        concatenated = "".join(
            str(expected_data[k])
            for k in sorted(expected_data.keys())
        )
        expected = hashlib.sha256(concatenated.encode()).hexdigest()

        assert token == expected

    def test_generate_token_ignores_existing_token(self):
        params = {
            "TerminalKey": "test_terminal",
            "OrderId": "1",
            "Token": "existing_token",
        }
        password = "secret"

        token = _generate_token(params, password)

        params_without = {"TerminalKey": "test_terminal", "OrderId": "1"}
        expected = _generate_token(params_without, password)

        assert token == expected

    def test_verify_token_correct(self):
        params = {
            "TerminalKey": "test_terminal",
            "OrderId": "1",
            "Status": "CONFIRMED",
        }
        password = "test_password"

        token = _generate_token(params, password)
        params["Token"] = token

        assert verify_token(params, password) is True

    def test_verify_token_wrong(self):
        params = {
            "TerminalKey": "test_terminal",
            "OrderId": "1",
            "Token": "wrong_token",
        }

        assert verify_token(params, "password") is False

    def test_verify_token_missing(self):
        params = {
            "TerminalKey": "test_terminal",
            "OrderId": "1",
        }

        assert verify_token(params, "password") is False

    def test_generate_token_order_independent(self):
        """Порядок ключей в dict не влияет на результат."""
        password = "secret"

        params1 = {"B": "2", "A": "1", "C": "3"}
        params2 = {"C": "3", "A": "1", "B": "2"}

        assert _generate_token(params1, password) == _generate_token(params2, password)
