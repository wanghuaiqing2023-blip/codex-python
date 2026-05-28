"""Tests for ChatGPT device auth login helpers."""

from __future__ import annotations

import io
import json
import base64
import unittest
from typing import Any
from urllib.error import HTTPError
from unittest.mock import patch

from pycodex.cli.login import AUTH_MODE_CHATGPT_AUTH_TOKENS
from pycodex.cli.parser import (
    _DEVICE_AUTH_DEFAULT_CLIENT_ID,
    _DEVICE_AUTH_DEFAULT_ISSUER,
    _exchange_device_auth_code,
    _poll_device_auth_token,
    _request_device_auth_user_code,
    _resolve_device_auth_client_id,
    _resolve_device_auth_issuer,
    _run_device_auth_login,
)


class _FakeTextResponse:
    def __init__(self, text: str):
        self._text = text.encode("utf-8")

    def __enter__(self) -> "_FakeTextResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        del exc_type
        del exc
        del tb

    def read(self) -> bytes:
        return self._text


class _BadResponse:
    def __init__(self, payload: str):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload.encode("utf-8")


class DeviceAuthTests(unittest.TestCase):
    def test_resolve_device_auth_defaults(self) -> None:
        self.assertEqual(_resolve_device_auth_issuer(None), _DEVICE_AUTH_DEFAULT_ISSUER)
        self.assertEqual(_resolve_device_auth_client_id(None), _DEVICE_AUTH_DEFAULT_CLIENT_ID)
        self.assertEqual(_resolve_device_auth_issuer(" "), _DEVICE_AUTH_DEFAULT_ISSUER)
        self.assertEqual(_resolve_device_auth_client_id(""), _DEVICE_AUTH_DEFAULT_CLIENT_ID)

    def test_request_device_auth_user_code_success(self) -> None:
        payload = {
            "device_auth_id": "device-id",
            "user_code": "ABC-123",
            "interval": 7,
        }

        with patch("pycodex.cli.parser.urlopen", return_value=_FakeTextResponse(json.dumps(payload))):
            data = _request_device_auth_user_code("https://auth.example.com/api/accounts", "client-id")

        self.assertEqual(data["device_auth_id"], "device-id")
        self.assertEqual(data["user_code"], "ABC-123")
        self.assertEqual(data["interval"], 7)

    def test_request_device_auth_user_code_rejects_missing_fields(self) -> None:
        payload = {"device_auth_id": "device-id", "interval": 5}

        with patch("pycodex.cli.parser.urlopen", return_value=_FakeTextResponse(json.dumps(payload))):
            with self.assertRaisesRegex(RuntimeError, "device code response is missing 'user_code'"):
                _request_device_auth_user_code("https://auth.example.com/api/accounts", "client-id")

    def test_request_device_auth_user_code_http_error(self) -> None:
        error = HTTPError(
            url="https://auth.example.com/api/accounts/deviceauth/usercode",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=_BadResponse("invalid"),
        )

        with patch("pycodex.cli.parser.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "device code request failed with status 400"):
                _request_device_auth_user_code("https://auth.example.com/api/accounts", "client-id")

    def test_request_device_auth_user_code_not_enabled(self) -> None:
        error = HTTPError(
            url="https://auth.example.com/api/accounts/deviceauth/usercode",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=_BadResponse("not available"),
        )

        with patch("pycodex.cli.parser.urlopen", side_effect=error):
            with self.assertRaisesRegex(
                RuntimeError,
                "device code login is not enabled for this Codex server",
            ):
                _request_device_auth_user_code("https://auth.example.com/api/accounts", "client-id")

    def test_poll_device_auth_token_returns_code_when_available(self) -> None:
        payload = {"authorization_code": "auth-code", "code_verifier": "code-verifier"}

        with patch("pycodex.cli.parser.urlopen", return_value=_FakeTextResponse(json.dumps(payload))):
            code_payload = _poll_device_auth_token(
                "https://auth.example.com/api/accounts",
                "device-id",
                "ABC-123",
                5,
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )

        self.assertEqual(code_payload["authorization_code"], "auth-code")
        self.assertEqual(code_payload["code_verifier"], "code-verifier")

    def test_poll_device_auth_token_retries_on_forbidden(self) -> None:
        request_count = 0
        token_body = {"authorization_code": "auth-code", "code_verifier": "code-verifier"}

        def _http_getter(*args: Any, **kwargs: Any):
            nonlocal request_count
            request_count += 1
            if request_count == 1:
                raise HTTPError(
                    url="https://auth.example.com/api/accounts/deviceauth/token",
                    code=403,
                    msg="Forbidden",
                    hdrs=None,
                    fp=_BadResponse("{}"),
                )
            return _FakeTextResponse(json.dumps(token_body))

        stderr = io.StringIO()
        with patch("pycodex.cli.parser._DEVICE_AUTH_MAX_WAIT_SECONDS", 1.0):
            with patch("pycodex.cli.parser.urlopen", side_effect=_http_getter):
                with patch("pycodex.cli.parser.time.sleep"):
                    code_payload = _poll_device_auth_token(
                        "https://auth.example.com/api/accounts",
                        "device-id",
                        "ABC-123",
                        1,
                        stdout=io.StringIO(),
                        stderr=stderr,
                    )

        self.assertEqual(code_payload["authorization_code"], "auth-code")
        self.assertEqual(request_count, 2)
        self.assertEqual(stderr.getvalue(), "")

    def test_poll_device_auth_token_retries_and_times_out_if_no_authorization(self) -> None:
        def _empty_payload(*args: Any, **kwargs: Any):
            del args
            del kwargs
            return _FakeTextResponse("{}")

        stderr = io.StringIO()
        with patch("pycodex.cli.parser._DEVICE_AUTH_MAX_WAIT_SECONDS", 0.0):
            with patch("pycodex.cli.parser.urlopen", side_effect=_empty_payload):
                with patch("pycodex.cli.parser.time.sleep"):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "device auth timed out after 15 minutes",
                    ):
                        _poll_device_auth_token(
                            "https://auth.example.com/api/accounts",
                            "device-id",
                            "ABC-123",
                            1,
                            stdout=io.StringIO(),
                            stderr=stderr,
                        )

        self.assertIn("Device auth timed out after 15 minutes.", stderr.getvalue())

    def test_poll_device_auth_token_invalid_json(self) -> None:
        with patch("pycodex.cli.parser.urlopen", return_value=_FakeTextResponse("not-json")):
            with self.assertRaisesRegex(RuntimeError, "device auth token response invalid JSON"):
                _poll_device_auth_token(
                    "https://auth.example.com/api/accounts",
                    "device-id",
                    "ABC-123",
                    1,
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )

    def test_poll_device_auth_token_times_out(self) -> None:
        def _forbidden(*args: Any, **kwargs: Any):
            raise HTTPError(
                url="https://auth.example.com/api/accounts/deviceauth/token",
                code=403,
                msg="Forbidden",
                hdrs=None,
                fp=_BadResponse("{}"),
            )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("pycodex.cli.parser._DEVICE_AUTH_MAX_WAIT_SECONDS", 0.0):
            with patch("pycodex.cli.parser.urlopen", side_effect=_forbidden):
                with patch("pycodex.cli.parser.time.sleep"):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "device auth timed out after 15 minutes",
                    ):
                        _poll_device_auth_token(
                            "https://auth.example.com/api/accounts",
                            "device-id",
                            "ABC-123",
                            1,
                            stdout=stdout,
                            stderr=stderr,
                        )

        self.assertIn("Device auth timed out after 15 minutes.", stderr.getvalue())

    def test_exchange_device_auth_code_success(self) -> None:
        payload = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "id_token": "header.payload.sig",
        }
        with patch("pycodex.cli.parser.urlopen", return_value=_FakeTextResponse(json.dumps(payload))):
            tokens = _exchange_device_auth_code(
                "https://auth.example.com",
                "client-id",
                "authorization-code",
                "code-verifier",
            )

        self.assertEqual(tokens["access_token"], "access-token")
        self.assertEqual(tokens["refresh_token"], "refresh-token")
        self.assertEqual(tokens["id_token"], "header.payload.sig")

    def test_run_device_auth_login_success(self) -> None:
        captured: list[Any] = []
        id_token_payload = {
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "acct-device",
            },
        }
        id_token = "header." + base64.urlsafe_b64encode(json.dumps(id_token_payload).encode()).decode("utf-8").rstrip("=") + ".sig"

        with patch("pycodex.cli.parser._request_device_auth_user_code") as request_user_code:
            request_user_code.return_value = {
                "device_auth_id": "device-id",
                "user_code": "ABC-123",
                "interval": 1,
            }
            with patch(
                "pycodex.cli.parser._poll_device_auth_token",
                return_value={"authorization_code": "auth-code", "code_verifier": "code-verifier"},
            ) as poll_code:
                with patch(
                    "pycodex.cli.parser._exchange_device_auth_code",
                    return_value={
                        "access_token": "access-token",
                        "refresh_token": "refresh-token",
                        "id_token": id_token,
                    },
                ) as exchange_code:
                    with patch("pycodex.cli.parser.write_auth_json", side_effect=lambda auth: captured.append(auth)):
                        code = _run_device_auth_login(
                            issuer="https://auth.example.com",
                            client_id="client-id",
                            stdout=io.StringIO(),
                            stderr=io.StringIO(),
                        )

        self.assertEqual(code, 0)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].auth_mode, AUTH_MODE_CHATGPT_AUTH_TOKENS)
        self.assertEqual(captured[0].tokens.get("access_token"), "access-token")
        self.assertEqual(captured[0].tokens.get("account_id"), "acct-device")
        self.assertEqual(request_user_code.call_count, 1)
        self.assertEqual(poll_code.call_count, 1)
        self.assertEqual(exchange_code.call_count, 1)

    def test_run_device_auth_login_request_user_code_error(self) -> None:
        stderr = io.StringIO()
        with patch(
            "pycodex.cli.parser._request_device_auth_user_code",
            side_effect=RuntimeError("device code request failed"),
        ):
            code = _run_device_auth_login(
                issuer="https://auth.example.com",
                client_id="client-id",
                stdout=io.StringIO(),
                stderr=stderr,
            )

        self.assertEqual(code, 2)
        self.assertIn("Error requesting device authorization: device code request failed", stderr.getvalue())

    def test_run_device_auth_login_exchange_error(self) -> None:
        stderr = io.StringIO()
        with patch(
            "pycodex.cli.parser._request_device_auth_user_code",
            return_value={
                "device_auth_id": "device-id",
                "user_code": "ABC-123",
                "interval": 1,
            },
        ):
            with patch(
                "pycodex.cli.parser._poll_device_auth_token",
                return_value={"authorization_code": "auth-code", "code_verifier": "code-verifier"},
            ):
                with patch(
                    "pycodex.cli.parser._exchange_device_auth_code",
                    side_effect=RuntimeError("exchange failed"),
                ):
                    code = _run_device_auth_login(
                        issuer="https://auth.example.com",
                        client_id="client-id",
                        stdout=io.StringIO(),
                        stderr=stderr,
                    )

        self.assertEqual(code, 2)
        self.assertIn("Device auth failed: exchange failed", stderr.getvalue())
