"""Tests for CLI chatgpt login helpers."""

from __future__ import annotations

import base64
import errno
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest
from unittest.mock import patch

from pycodex.cli.login import (
    AUTH_MODE_CHATGPT,
    ACCESS_TOKEN_STDIN_EMPTY_MESSAGE,
    ACCESS_TOKEN_STDIN_READING_MESSAGE,
    ACCESS_TOKEN_STDIN_TERMINAL_MESSAGE,
    API_KEY_STDIN_EMPTY_MESSAGE,
    API_KEY_STDIN_READING_MESSAGE,
    API_KEY_STDIN_TERMINAL_MESSAGE,
    _CHATGPT_LOGIN_DEFAULT_PORT,
    _CHATGPT_LOGIN_FALLBACK_PORT,
    access_token_from_stdin_text,
    api_key_from_stdin_text,
    device_code_fallback_message,
    _exchange_authorization_code,
    _extract_auth_claims_from_jwt,
    _make_callback_handler,
    login_log_file_path,
    login_config_error_message,
    _ChatgptCallbackState,
    login_status_error_message,
    login_status_message,
    login_disabled_message,
    login_log_default_filter,
    login_log_open_options,
    login_log_unix_file_mode,
    login_log_warning_message,
    login_result_message,
    logout_status_message,
    print_login_server_start,
    run_chatgpt_login,
    safe_format_key,
    stdin_secret_messages,
    stdin_secret_read_error_message,
)


class _FakeCallbackResult:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self.body = body


def _request(port: int, path: str) -> _FakeCallbackResult:
    request = Request(f"http://127.0.0.1:{port}{path}")
    try:
        with urlopen(request, timeout=1) as response:
            return _FakeCallbackResult(response.status, response.read())
    except HTTPError as exc:
        return _FakeCallbackResult(exc.code, exc.read())


class LoginCallbackHandlerTests(unittest.TestCase):
    def test_print_login_server_start_matches_rust_message_shape(self) -> None:
        # Rust parity: codex-cli/src/login.rs print_login_server_start.
        stderr = FakeStdErr()

        print_login_server_start(stderr, 1455, "https://auth.example.com/oauth")

        self.assertEqual(
            stderr.value,
            (
                "Starting local login server on http://localhost:1455.\n"
                "If your browser did not open, navigate to this URL to authenticate:\n"
                "\n"
                "https://auth.example.com/oauth\n"
                "\n"
                "On a remote or headless machine? Use `codex login --device-auth` instead.\n"
            ),
        )

    def test_login_disabled_messages_match_rust_forced_method_guards(self) -> None:
        # Rust parity: codex-cli/src/login.rs forced_login_method guards.
        self.assertEqual(
            login_disabled_message("chatgpt", "api"),
            "ChatGPT login is disabled. Use API key login instead.",
        )
        self.assertEqual(
            login_disabled_message("device-code", "api"),
            "ChatGPT login is disabled. Use API key login instead.",
        )
        self.assertEqual(
            login_disabled_message("api-key", "chatgpt"),
            "API key login is disabled. Use ChatGPT login instead.",
        )
        self.assertEqual(
            login_disabled_message("access-token", "api"),
            "Access token login is disabled. Use API key login instead.",
        )
        self.assertIsNone(login_disabled_message("chatgpt", "chatgpt"))
        self.assertIsNone(login_disabled_message("api-key", "api"))
        self.assertIsNone(login_disabled_message("access-token", "chatgpt"))

    def test_stdin_secret_text_matches_rust_trim_and_empty_messages(self) -> None:
        # Rust parity: codex-cli/src/login.rs read_api_key_from_stdin/read_access_token_from_stdin.
        self.assertEqual(api_key_from_stdin_text("  sk-test\n"), "sk-test")
        self.assertEqual(access_token_from_stdin_text("\taccess-token\r\n"), "access-token")
        with self.assertRaisesRegex(ValueError, API_KEY_STDIN_EMPTY_MESSAGE):
            api_key_from_stdin_text(" \n\t")
        with self.assertRaisesRegex(ValueError, ACCESS_TOKEN_STDIN_EMPTY_MESSAGE):
            access_token_from_stdin_text("")

    def test_stdin_secret_messages_match_rust_login_prompts(self) -> None:
        # Rust parity: codex-cli/src/login.rs read_api_key_from_stdin/read_access_token_from_stdin.
        self.assertEqual(
            stdin_secret_messages("api-key"),
            (
                API_KEY_STDIN_TERMINAL_MESSAGE,
                API_KEY_STDIN_READING_MESSAGE,
                API_KEY_STDIN_EMPTY_MESSAGE,
            ),
        )
        self.assertEqual(
            stdin_secret_messages("access-token"),
            (
                ACCESS_TOKEN_STDIN_TERMINAL_MESSAGE,
                ACCESS_TOKEN_STDIN_READING_MESSAGE,
                ACCESS_TOKEN_STDIN_EMPTY_MESSAGE,
            ),
        )
        with self.assertRaisesRegex(ValueError, "Unknown stdin secret kind"):
            stdin_secret_messages("password")

    def test_stdin_secret_read_error_message_matches_rust(self) -> None:
        # Rust parity: codex-cli/src/login.rs read_stdin_secret read_to_string error path.
        self.assertEqual(
            stdin_secret_read_error_message("stream closed"),
            "Failed to read stdin: stream closed",
        )

    def test_login_status_messages_match_rust_auth_mode_output(self) -> None:
        # Rust parity: codex-cli/src/login.rs run_login_status.
        self.assertEqual(
            login_status_message("apiKey", "sk-proj-1234567890ABCDE"),
            "Logged in using an API key - sk-proj-***ABCDE",
        )
        self.assertEqual(login_status_message("chatgpt"), "Logged in using ChatGPT")
        self.assertEqual(login_status_message("chatgptAuthTokens"), "Logged in using ChatGPT")
        self.assertEqual(login_status_message("agentIdentity"), "Logged in using access token")
        self.assertEqual(login_status_message(None), "Not logged in")
        with self.assertRaisesRegex(ValueError, "API key auth requires an API key"):
            login_status_message("apiKey")

    def test_login_status_error_messages_match_rust(self) -> None:
        # Rust parity: codex-cli/src/login.rs run_login_status error branches.
        self.assertEqual(
            login_status_error_message("api-key-retrieval", RuntimeError("keychain offline")),
            "Unexpected error retrieving API key: keychain offline",
        )
        self.assertEqual(
            login_status_error_message("auth-status", RuntimeError("auth file denied")),
            "Error checking login status: auth file denied",
        )
        with self.assertRaisesRegex(ValueError, "Unknown login status error stage"):
            login_status_error_message("logout", RuntimeError("bad"))

    def test_logout_status_messages_match_rust_logout_output(self) -> None:
        # Rust parity: codex-cli/src/login.rs run_logout.
        self.assertEqual(logout_status_message(True), "Successfully logged out")
        self.assertEqual(logout_status_message(False), "Not logged in")
        self.assertEqual(
            logout_status_message(False, RuntimeError("revoke failed")),
            "Error logging out: revoke failed",
        )

    def test_login_result_messages_match_rust_flow_output(self) -> None:
        # Rust parity: codex-cli/src/login.rs run_login_with_* result handling.
        self.assertEqual(login_result_message("chatgpt"), "Successfully logged in")
        self.assertEqual(login_result_message("api-key"), "Successfully logged in")
        self.assertEqual(
            login_result_message("chatgpt", RuntimeError("browser failed")),
            "Error logging in: browser failed",
        )
        self.assertEqual(
            login_result_message("api-key", RuntimeError("bad key")),
            "Error logging in: bad key",
        )
        self.assertEqual(
            login_result_message("access-token", RuntimeError("expired")),
            "Error logging in with access token: expired",
        )
        self.assertEqual(
            login_result_message("device-code", RuntimeError("denied")),
            "Error logging in with device code: denied",
        )

    def test_device_code_fallback_message_matches_rust_not_found_branch(self) -> None:
        # Rust parity: codex-cli/src/login.rs run_login_with_device_code_fallback_to_browser.
        self.assertEqual(
            device_code_fallback_message("not_found"),
            "Device code login is not enabled; falling back to browser login.",
        )
        self.assertIsNone(device_code_fallback_message("permission_denied"))

    def test_login_config_error_messages_match_rust_load_config_or_exit(self) -> None:
        # Rust parity: codex-cli/src/login.rs load_config_or_exit.
        self.assertEqual(
            login_config_error_message("parse-overrides", RuntimeError("bad -c")),
            "Error parsing -c overrides: bad -c",
        )
        self.assertEqual(
            login_config_error_message("load-config", RuntimeError("missing config")),
            "Error loading configuration: missing config",
        )
        with self.assertRaisesRegex(ValueError, "Unknown login config error stage"):
            login_config_error_message("auth", RuntimeError("bad"))

    def test_login_log_file_path_matches_rust_login_logging_filename(self) -> None:
        # Rust parity: codex-cli/src/login.rs init_login_file_logging.
        self.assertEqual(
            login_log_file_path(Path("/tmp/codex/log")),
            Path("/tmp/codex/log") / "codex-login.log",
        )

    def test_login_log_default_filter_matches_rust_login_logging_filter(self) -> None:
        # Rust parity: codex-cli/src/login.rs init_login_file_logging.
        self.assertEqual(
            login_log_default_filter(None),
            "codex_cli=info,codex_core=info,codex_login=info",
        )
        self.assertEqual(
            login_log_default_filter("codex_login=debug"),
            "codex_login=debug",
        )
        self.assertEqual(
            login_log_default_filter("   "),
            "codex_cli=info,codex_core=info,codex_login=info",
        )

    def test_login_log_unix_file_mode_matches_rust_open_options(self) -> None:
        # Rust parity: codex-cli/src/login.rs init_login_file_logging.
        self.assertEqual(login_log_unix_file_mode(is_unix=True), 0o600)
        self.assertIsNone(login_log_unix_file_mode(is_unix=False))

    def test_login_log_open_options_match_rust(self) -> None:
        # Rust parity: codex-cli/src/login.rs init_login_file_logging.
        self.assertEqual(
            login_log_open_options(is_unix=True),
            {"create": True, "append": True, "mode": 0o600},
        )
        self.assertEqual(
            login_log_open_options(is_unix=False),
            {"create": True, "append": True},
        )

    def test_login_log_warning_messages_match_rust_login_logging_warnings(self) -> None:
        # Rust parity: codex-cli/src/login.rs init_login_file_logging.
        log_dir = Path("/tmp/codex/log")
        log_path = log_dir / "codex-login.log"

        self.assertEqual(
            login_log_warning_message("resolve-log-dir", RuntimeError("bad home")),
            "Warning: failed to resolve login log directory: bad home",
        )
        self.assertEqual(
            login_log_warning_message("create-log-dir", RuntimeError("denied"), log_dir),
            f"Warning: failed to create login log directory {log_dir}: denied",
        )
        self.assertEqual(
            login_log_warning_message("open-log-file", RuntimeError("locked"), log_path),
            f"Warning: failed to open login log file {log_path}: locked",
        )
        self.assertEqual(
            login_log_warning_message("init-log-file", RuntimeError("subscriber set"), log_path),
            f"Warning: failed to initialize login log file {log_path}: subscriber set",
        )
        with self.assertRaisesRegex(ValueError, "path is required"):
            login_log_warning_message("open-log-file", RuntimeError("locked"))

    def test_safe_format_key_matches_rust_login_status_masking(self) -> None:
        # Rust parity: codex-cli/src/login.rs safe_format_key.
        self.assertEqual(safe_format_key("sk-proj-1234567890ABCDE"), "sk-proj-***ABCDE")
        self.assertEqual(safe_format_key("sk-proj-12345"), "***")
        self.assertEqual(safe_format_key("1234567890123"), "***")
        self.assertEqual(safe_format_key("12345678901234"), "12345678***01234")

    def test_callback_handler_mark_cancel(self) -> None:
        callback_state = _ChatgptCallbackState(expected_state="expected")
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _make_callback_handler(callback_state),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        try:
            thread.start()
            result = _request(server.server_address[1], "/cancel")
            self.assertTrue(callback_state.done.wait(1))
            self.assertEqual(callback_state.error, "login_cancelled")
            self.assertEqual(callback_state.error_message, "Login cancelled")
            self.assertEqual(result.status, 200)
            self.assertIn("Login cancelled", result.body.decode("utf-8"))
            self.assertTrue(callback_state.done.is_set())
        finally:
            server.shutdown()
            thread.join(timeout=1)
            server.server_close()

    def test_callback_handler_marks_success_page(self) -> None:
        callback_state = _ChatgptCallbackState(expected_state="expected")
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _make_callback_handler(callback_state),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        try:
            thread.start()
            result = _request(server.server_address[1], "/success")
            self.assertEqual(result.status, 200)
            self.assertIn("Login completed", result.body.decode("utf-8"))
            self.assertFalse(callback_state.done.is_set())
        finally:
            server.shutdown()
            thread.join(timeout=1)
            server.server_close()

    def test_callback_handler_accepts_matching_state_and_code(self) -> None:
        callback_state = _ChatgptCallbackState(expected_state="expected")
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _make_callback_handler(callback_state),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        try:
            thread.start()
            result = _request(
                server.server_address[1],
                "/auth/callback?state=expected&code=abc123",
            )
            self.assertEqual(result.status, 200)
            self.assertEqual(callback_state.code, "abc123")
            self.assertEqual(callback_state.error, None)
            self.assertIn("Login completed", result.body.decode("utf-8"))
        finally:
            server.shutdown()
            thread.join(timeout=1)
            server.server_close()

    def test_callback_handler_rejects_mismatched_state(self) -> None:
        callback_state = _ChatgptCallbackState(expected_state="expected")
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _make_callback_handler(callback_state),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        try:
            thread.start()
            result = _request(
                server.server_address[1],
                "/auth/callback?state=unexpected&code=abc123",
            )
            self.assertEqual(result.status, 400)
            self.assertEqual(callback_state.error, "state_mismatch")
            self.assertEqual(callback_state.error_message, "State mismatch")
            self.assertIn("State mismatch", result.body.decode("utf-8"))
        finally:
            server.shutdown()
            thread.join(timeout=1)
            server.server_close()

    def test_extract_auth_claims_from_jwt_empty_for_invalid(self) -> None:
        self.assertEqual(_extract_auth_claims_from_jwt("bad.token"), {})

    def test_extract_auth_claims_from_jwt_extracts_nested_auth(self) -> None:
        claims = {
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "acct-1",
                "plan": "plus",
            },
        }
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        token = f"header.{payload}.signature"

        self.assertEqual(
            _extract_auth_claims_from_jwt(token),
            {
                "chatgpt_account_id": "acct-1",
                "plan": "plus",
            },
        )


class RunChatgptLoginTests(unittest.TestCase):
    def test_run_chatgpt_login_stores_account_id_when_present_in_id_token(self) -> None:
        class FakeServer:
            def __init__(self) -> None:
                self.server_address = ("127.0.0.1", _CHATGPT_LOGIN_DEFAULT_PORT)

            def shutdown(self) -> None:
                pass

            def server_close(self) -> None:
                pass

        class FakeThread:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self._started = False

            def start(self) -> None:
                self._started = True

            def is_alive(self) -> bool:
                return self._started

            def join(self, timeout: float | None = None) -> None:
                del timeout
                self._started = False

        captured_auth: list[Any] = []

        claims = {
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "acct-1",
            },
        }
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        id_token = f"header.{payload}.signature"
        exchange_result = {
            "access_token": "access-token-value",
            "refresh_token": "refresh-token-value",
            "id_token": id_token,
        }

        with patch("pycodex.cli.login.ThreadingHTTPServer", return_value=FakeServer()) as _server:
            with patch("pycodex.cli.login.threading.Thread", return_value=FakeThread()) as _thread:
                with patch("pycodex.cli.login._wait_for_callback") as wait_for_callback:
                    with patch(
                        "pycodex.cli.login._exchange_authorization_code",
                        return_value=exchange_result,
                    ) as exchange:
                        with patch("pycodex.cli.login.write_auth_json", side_effect=lambda auth: captured_auth.append(auth)):
                            with patch("pycodex.cli.login.webbrowser.open", return_value=True):
                                with patch("pycodex.cli.login._CHATGPT_LOGIN_WAIT_SECONDS", 0):
                                    def _complete_callback(state, _timeout):
                                        state.code = "code-value"
                                        state.done.set()
                                        return True

                                    wait_for_callback.side_effect = _complete_callback
                                    code = run_chatgpt_login(stdout=None, stderr=FakeStdErr())  # type: ignore[arg-type]

        self.assertEqual(code, 0)
        self.assertEqual(len(captured_auth), 1)
        self.assertEqual(captured_auth[0].auth_mode, AUTH_MODE_CHATGPT)
        self.assertEqual(captured_auth[0].tokens.get("access_token"), "access-token-value")
        self.assertEqual(captured_auth[0].tokens.get("account_id"), "acct-1")
        self.assertEqual(len(_server.call_args_list), 1)
        self.assertEqual(len(exchange.call_args_list), 1)

    def test_run_chatgpt_login_falls_back_to_secondary_port(self) -> None:
        created_ports: list[int] = []
        fail_default_port = {"value": True}

        class FakeServer:
            def __init__(self, port: int) -> None:
                self.server_address = ("127.0.0.1", port)

            def shutdown(self) -> None:
                pass

            def server_close(self) -> None:
                pass

        class FakeThread:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self._started = False

            def start(self) -> None:
                self._started = True

            def is_alive(self) -> bool:
                return self._started

            def join(self, timeout: float | None = None) -> None:
                del timeout
                self._started = False

        class FakeSocket:
            def __enter__(self) -> "FakeSocket":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
                del exc_type
                del exc
                del tb

            def sendall(self, payload: bytes) -> None:
                del payload

        def server_factory(address: tuple[str, int], _handler: type[BaseHTTPRequestHandler]) -> FakeServer:
            created_ports.append(address[1])
            if address[1] == _CHATGPT_LOGIN_DEFAULT_PORT and fail_default_port["value"]:
                fail_default_port["value"] = False
                raise OSError(errno.EADDRINUSE, "Address already in use")
            return FakeServer(address[1])

        with patch("pycodex.cli.login.ThreadingHTTPServer", side_effect=server_factory):
            with patch("pycodex.cli.login.threading.Thread", return_value=FakeThread()):
                with patch("pycodex.cli.login.time.sleep"):
                    with patch("pycodex.cli.login._wait_for_callback") as wait_for_callback:
                        with patch(
                            "pycodex.cli.login._exchange_authorization_code",
                            return_value={"access_token": "access"},
                        ):
                            with patch("pycodex.cli.login.socket.create_connection", return_value=FakeSocket()):
                                with patch("pycodex.cli.login.webbrowser.open", return_value=True):
                                    with patch("pycodex.cli.login.write_auth_json"):
                                        with patch("pycodex.cli.login._CHATGPT_LOGIN_WAIT_SECONDS", 0):
                                            def _complete_callback(state, _timeout):
                                                state.code = "code-value"
                                                state.done.set()
                                                return True

                                            wait_for_callback.side_effect = _complete_callback
                                            code = run_chatgpt_login(stdout=None, stderr=FakeStdErr())  # type: ignore[arg-type]

        self.assertEqual(code, 0)
        self.assertEqual(created_ports, [_CHATGPT_LOGIN_DEFAULT_PORT, _CHATGPT_LOGIN_FALLBACK_PORT])

    def test_run_chatgpt_login_returns_error_when_callback_times_out(self) -> None:
        class FakeServer:
            def __init__(self) -> None:
                self.server_address = ("127.0.0.1", _CHATGPT_LOGIN_DEFAULT_PORT)

            def shutdown(self) -> None:
                pass

            def server_close(self) -> None:
                pass

        class FakeThread:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self._started = False

            def start(self) -> None:
                self._started = True

            def is_alive(self) -> bool:
                return self._started

            def join(self, timeout: float | None = None) -> None:
                del timeout
                self._started = False

        stderr = FakeStdErr()
        with patch("pycodex.cli.login.ThreadingHTTPServer", return_value=FakeServer()):
            with patch("pycodex.cli.login.threading.Thread", return_value=FakeThread()):
                with patch("pycodex.cli.login._wait_for_callback", return_value=False):
                    with patch("pycodex.cli.login.webbrowser.open", return_value=True):
                        with patch("pycodex.cli.login._CHATGPT_LOGIN_WAIT_SECONDS", 0):
                            code = run_chatgpt_login(stdout=None, stderr=stderr)  # type: ignore[arg-type]

        self.assertEqual(code, 64)
        self.assertIn("login callback was not completed in time", stderr.value)

    def test_run_chatgpt_login_uses_special_error_message(self) -> None:
        class FakeServer:
            def __init__(self) -> None:
                self.server_address = ("127.0.0.1", _CHATGPT_LOGIN_DEFAULT_PORT)

            def shutdown(self) -> None:
                pass

            def server_close(self) -> None:
                pass

        class FakeThread:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self._started = False

            def start(self) -> None:
                self._started = True

            def is_alive(self) -> bool:
                return self._started

            def join(self, timeout: float | None = None) -> None:
                del timeout
                self._started = False

        stderr = FakeStdErr()
        with patch("pycodex.cli.login.ThreadingHTTPServer", return_value=FakeServer()):
            with patch("pycodex.cli.login.threading.Thread", return_value=FakeThread()):
                with patch("pycodex.cli.login._wait_for_callback") as wait_for_callback:
                    with patch("pycodex.cli.login.webbrowser.open", return_value=True):
                        with patch("pycodex.cli.login._CHATGPT_LOGIN_WAIT_SECONDS", 0):
                            def _error_callback(state, _timeout):
                                state.error = "access_denied"
                                state.error_description = "missing_codex_entitlement"
                                state.error_message = (
                                    "Codex is not enabled for your workspace. "
                                    "Contact your workspace administrator to request access to Codex."
                                )
                                state.done.set()
                                return True

                            wait_for_callback.side_effect = _error_callback
                            code = run_chatgpt_login(stdout=None, stderr=stderr)  # type: ignore[arg-type]

        self.assertEqual(code, 64)
        self.assertIn("Error logging in: Codex is not enabled for your workspace.", stderr.value)


class FakeStdErr:
    def __init__(self) -> None:
        self.value = ""

    def write(self, text: str) -> None:
        self.value += str(text)


class ExchangeAuthorizationCodeTests(unittest.TestCase):
    def test_exchange_authorization_code_success(self) -> None:
        response_body = {
            "access_token": "access-token-value",
            "refresh_token": "refresh-token-value",
            "id_token": "header.payload.sig",
        }
        response_body_bytes = json.dumps(response_body).encode()

        class _FakeResponse:
            def __enter__(self) -> "_FakeResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
                del exc_type
                del exc
                del tb

            def read(self) -> bytes:
                return response_body_bytes

        with patch("pycodex.cli.login.urlopen", return_value=_FakeResponse()) as mocked_urlopen:
            tokens = _exchange_authorization_code(
                issuer="https://auth.example.com",
                client_id="client-id",
                redirect_uri="http://127.0.0.1:1455/auth/callback",
                code_verifier="verifier",
                code="code",
            )

        self.assertEqual(tokens["access_token"], "access-token-value")
        self.assertEqual(tokens["refresh_token"], "refresh-token-value")
        self.assertEqual(tokens["id_token"], "header.payload.sig")
        self.assertEqual(mocked_urlopen.call_count, 1)

    def test_exchange_authorization_code_propagates_http_error(self) -> None:
        class _BadResponse:
            def read(self) -> bytes:
                return b'{"error":"invalid_grant"}'

            def close(self) -> None:
                return None

        error = HTTPError(
            url="https://auth.example.com/oauth/token",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=_BadResponse(),
        )

        with patch("pycodex.cli.login.urlopen", side_effect=error):
            with self.assertRaises(RuntimeError) as exc:
                _exchange_authorization_code(
                    issuer="https://auth.example.com",
                    client_id="client-id",
                    redirect_uri="http://127.0.0.1:1455/auth/callback",
                    code_verifier="verifier",
                    code="code",
                )

        self.assertIn("token exchange failed with status 400", str(exc.exception))
        self.assertIn("invalid_grant", str(exc.exception))
