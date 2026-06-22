from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError

import pytest

from pycodex.login.device_code_auth import (
    DEVICE_CODE_NOT_ENABLED_MESSAGE,
    CodeSuccessResp,
    DeviceCode,
    ServerOptions,
    UserCodeResp,
    deserialize_interval,
    poll_for_token,
    print_device_code_prompt,
    request_device_code,
    request_user_code,
)


class _FakeResponse:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        del exc_type, exc, tb

    def read(self) -> bytes:
        return self.payload.encode("utf-8")


class _BadResponse:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload.encode("utf-8")

    def close(self) -> None:
        self.payload = ""


def _http_error(code: int, body: str = "{}") -> HTTPError:
    return HTTPError("https://auth.example.com", code, "status", None, _BadResponse(body))


def test_deserialize_interval_matches_rust_string_parser():
    # Rust crate: codex-login
    # Rust module: src/device_code_auth.rs
    # Contract: deserialize_interval trims and parses string intervals.
    assert deserialize_interval(" 7 ") == 7
    assert deserialize_interval(7) == 7
    with pytest.raises(ValueError):
        deserialize_interval("not-int")


def test_request_user_code_posts_client_id_and_accepts_usercode_alias():
    # Rust contract: request_user_code posts to /deviceauth/usercode and accepts usercode alias.
    captured: list[Any] = []

    def opener(request, timeout):
        captured.append((request.full_url, request.data, timeout, request.headers))
        return _FakeResponse(json.dumps({"device_auth_id": "device-id", "usercode": "ABC-123", "interval": "5"}))

    response = request_user_code("https://auth.example.com/api/accounts", "client-id", opener=opener)

    assert response == UserCodeResp(device_auth_id="device-id", user_code="ABC-123", interval=5)
    assert captured[0][0] == "https://auth.example.com/api/accounts/deviceauth/usercode"
    assert json.loads(captured[0][1].decode("utf-8")) == {"client_id": "client-id"}


def test_request_user_code_404_is_not_enabled():
    # Rust contract: 404 usercode response maps to the not-enabled message.
    def opener(request, timeout):
        raise _http_error(404)

    with pytest.raises(FileNotFoundError, match="device code login is not enabled"):
        request_user_code("https://auth.example.com/api/accounts", "client-id", opener=opener)

    assert DEVICE_CODE_NOT_ENABLED_MESSAGE.startswith("device code login is not enabled")


def test_request_user_code_rejects_missing_user_code():
    # Rust contract: malformed user-code JSON is rejected during response decoding.
    def opener(request, timeout):
        return _FakeResponse(json.dumps({"device_auth_id": "device-id", "interval": "5"}))

    with pytest.raises(OSError, match="missing 'user_code'"):
        request_user_code("https://auth.example.com/api/accounts", "client-id", opener=opener)


def test_poll_for_token_returns_authorization_code_and_pkce():
    # Rust contract: success response returns CodeSuccessResp.
    def opener(request, timeout):
        return _FakeResponse(
            json.dumps(
                {
                    "authorization_code": "auth-code",
                    "code_challenge": "challenge",
                    "code_verifier": "verifier",
                }
            )
        )

    assert poll_for_token("https://auth.example.com/api/accounts", "device-id", "ABC-123", 5, opener=opener) == CodeSuccessResp(
        authorization_code="auth-code",
        code_challenge="challenge",
        code_verifier="verifier",
    )


def test_poll_for_token_retries_on_forbidden_then_succeeds():
    # Rust contract: 403/404 responses are authorization-pending states until timeout.
    calls = 0
    sleeps: list[float] = []
    now = 0.0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _http_error(403)
        return _FakeResponse(json.dumps({"authorization_code": "auth-code", "code_verifier": "verifier"}))

    def clock() -> float:
        return now

    poll_for_token(
        "https://auth.example.com/api/accounts",
        "device-id",
        "ABC-123",
        2,
        opener=opener,
        sleep=sleeps.append,
        clock=clock,
        max_wait_seconds=10,
    )

    assert calls == 2
    assert sleeps == [2.0]


def test_poll_for_token_times_out_after_max_wait():
    # Rust contract: pending auth times out after the 15-minute window.
    def opener(request, timeout):
        raise _http_error(404)

    times = iter([0.0, 20.0])

    with pytest.raises(TimeoutError, match="device auth timed out after 15 minutes"):
        poll_for_token(
            "https://auth.example.com/api/accounts",
            "device-id",
            "ABC-123",
            1,
            opener=opener,
            sleep=lambda seconds: None,
            clock=lambda: next(times),
            max_wait_seconds=10,
        )


def test_print_device_code_prompt_contains_url_code_and_warning():
    # Rust contract: prompt includes verification URL, code, and phishing warning.
    prompt = print_device_code_prompt("https://auth.example.com/codex/device", "ABC-123", version="1.2.3")

    assert "Welcome to Codex" in prompt
    assert "https://auth.example.com/codex/device" in prompt
    assert "ABC-123" in prompt
    assert "Never share this code" in prompt


def test_request_device_code_derives_api_base_and_verification_url():
    # Rust contract: request_device_code trims issuer and uses /api/accounts plus /codex/device.
    def opener(request, timeout):
        assert request.full_url == "https://auth.example.com/api/accounts/deviceauth/usercode"
        return _FakeResponse(json.dumps({"device_auth_id": "device-id", "user_code": "ABC-123", "interval": "7"}))

    opts = ServerOptions(issuer="https://auth.example.com/", client_id="client-id")

    assert request_device_code(opts, opener=opener) == DeviceCode(
        verification_url="https://auth.example.com/codex/device",
        user_code="ABC-123",
        device_auth_id="device-id",
        interval=7,
    )
