"""Port of Rust ``codex-login::device_code_auth``.

Rust source:
- ``codex/codex-rs/login/src/device_code_auth.rs``
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pycodex.login.pkce import PkceCodes
from pycodex.login.server import (
    ServerOptions,
    ensure_workspace_allowed as server_ensure_workspace_allowed,
    exchange_code_for_tokens as server_exchange_code_for_tokens,
    persist_tokens_async as server_persist_tokens_async,
)


ANSI_BLUE = "\x1b[94m"
ANSI_GRAY = "\x1b[90m"
ANSI_RESET = "\x1b[0m"
DEFAULT_DEVICE_AUTH_MAX_WAIT_SECONDS = 15 * 60
DEVICE_CODE_NOT_ENABLED_MESSAGE = (
    "device code login is not enabled for this Codex server. "
    "Use the browser login or verify the server URL."
)


@dataclass(frozen=True)
class DeviceCode:
    verification_url: str
    user_code: str
    device_auth_id: str
    interval: int


@dataclass(frozen=True)
class UserCodeResp:
    device_auth_id: str
    user_code: str
    interval: int = 0


@dataclass(frozen=True)
class CodeSuccessResp:
    authorization_code: str
    code_challenge: str
    code_verifier: str


class _ReadableResponse(Protocol):
    def read(self) -> bytes:
        ...


OpenUrl = Callable[..., Any]
Sleep = Callable[[float], None]
Clock = Callable[[], float]


def deserialize_interval(value: Any) -> int:
    if isinstance(value, str):
        return int(value.strip())
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise TypeError("interval must be a string or integer")


def request_user_code(
    auth_base_url: str,
    client_id: str,
    *,
    opener: OpenUrl = urlopen,
    timeout: float = 30,
) -> UserCodeResp:
    body = json.dumps({"client_id": client_id}).encode("utf-8")
    request = Request(
        url=f"{auth_base_url}/deviceauth/usercode",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "pycodex"},
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        if exc.code == 404:
            _drain_http_error(exc)
            raise FileNotFoundError(DEVICE_CODE_NOT_ENABLED_MESSAGE) from exc
        _drain_http_error(exc)
        raise OSError(f"device code request failed with status {exc.code}") from exc
    except URLError as exc:
        raise OSError(f"device code request failed: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OSError(f"device code request returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise OSError("device code request returned an unexpected response.")

    device_auth_id = payload.get("device_auth_id")
    if not isinstance(device_auth_id, str) or not device_auth_id.strip():
        raise OSError("device code response is missing 'device_auth_id'.")
    user_code = payload.get("user_code", payload.get("usercode"))
    if not isinstance(user_code, str) or not user_code.strip():
        raise OSError("device code response is missing 'user_code'.")

    interval = payload.get("interval", 0)
    return UserCodeResp(
        device_auth_id=device_auth_id.strip(),
        user_code=user_code.strip(),
        interval=deserialize_interval(interval),
    )


def poll_for_token(
    auth_base_url: str,
    device_auth_id: str,
    user_code: str,
    interval: int,
    *,
    opener: OpenUrl = urlopen,
    sleep: Sleep = time.sleep,
    clock: Clock = time.monotonic,
    max_wait_seconds: float = DEFAULT_DEVICE_AUTH_MAX_WAIT_SECONDS,
    timeout: float = 30,
) -> CodeSuccessResp:
    body = json.dumps({"device_auth_id": device_auth_id, "user_code": user_code}).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "pycodex"}
    start = clock()

    while True:
        request = Request(
            url=f"{auth_base_url}/deviceauth/token",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with opener(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
            if not raw.strip():
                raise OSError("empty token response")
            payload = json.loads(raw)
        except HTTPError as exc:
            if exc.code in {403, 404}:
                _drain_http_error(exc)
                elapsed = clock() - start
                if elapsed >= max_wait_seconds:
                    raise TimeoutError("device auth timed out after 15 minutes") from exc
                sleep_for = min(float(interval), max_wait_seconds - elapsed)
                sleep(sleep_for)
                continue
            _drain_http_error(exc)
            raise OSError(f"device auth failed with status {exc.code}") from exc
        except URLError as exc:
            raise OSError(f"device auth token request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise OSError(f"device auth token response invalid JSON: {exc}") from exc

        if isinstance(payload, dict):
            authorization_code = payload.get("authorization_code")
            code_challenge = payload.get("code_challenge", "")
            code_verifier = payload.get("code_verifier")
            if isinstance(authorization_code, str) and isinstance(code_verifier, str):
                return CodeSuccessResp(
                    authorization_code=authorization_code,
                    code_challenge=code_challenge if isinstance(code_challenge, str) else "",
                    code_verifier=code_verifier,
                )

        elapsed = clock() - start
        if elapsed >= max_wait_seconds:
            raise TimeoutError("device auth timed out after 15 minutes")
        sleep(min(float(interval), max_wait_seconds - elapsed))


def print_device_code_prompt(verification_url: str, code: str, *, version: str = "") -> str:
    return (
        f"\nWelcome to Codex [v{ANSI_GRAY}{version}{ANSI_RESET}]\n"
        f"{ANSI_GRAY}OpenAI's command-line coding agent{ANSI_RESET}\n"
        "\nFollow these steps to sign in with ChatGPT using device code authorization:\n"
        f"\n1. Open this link in your browser and sign in to your account\n   {ANSI_BLUE}{verification_url}{ANSI_RESET}\n"
        f"\n2. Enter this one-time code {ANSI_GRAY}(expires in 15 minutes){ANSI_RESET}\n   {ANSI_BLUE}{code}{ANSI_RESET}\n"
        f"\n{ANSI_GRAY}Device codes are a common phishing target. Never share this code.{ANSI_RESET}\n"
    )


def request_device_code(opts: ServerOptions, *, opener: OpenUrl = urlopen) -> DeviceCode:
    base_url = opts.issuer.rstrip("/")
    api_base_url = f"{base_url}/api/accounts"
    user_code = request_user_code(api_base_url, opts.client_id, opener=opener)
    return DeviceCode(
        verification_url=f"{base_url}/codex/device",
        user_code=user_code.user_code,
        device_auth_id=user_code.device_auth_id,
        interval=user_code.interval,
    )


async def complete_device_code_login(
    opts: ServerOptions,
    device_code: DeviceCode,
    *,
    exchange_code_for_tokens: Callable[..., Any] | None = None,
    ensure_workspace_allowed: Callable[..., Any] | None = None,
    persist_tokens_async: Callable[..., Any] | None = None,
    opener: OpenUrl = urlopen,
) -> Any:
    if exchange_code_for_tokens is None:
        exchange_code_for_tokens = server_exchange_code_for_tokens
    if ensure_workspace_allowed is None:
        ensure_workspace_allowed = server_ensure_workspace_allowed
    if persist_tokens_async is None:
        persist_tokens_async = server_persist_tokens_async
    base_url = opts.issuer.rstrip("/")
    api_base_url = f"{base_url}/api/accounts"
    code_resp = await asyncio.to_thread(
        poll_for_token,
        api_base_url,
        device_code.device_auth_id,
        device_code.user_code,
        device_code.interval,
        opener=opener,
    )
    pkce = PkceCodes(code_verifier=code_resp.code_verifier, code_challenge=code_resp.code_challenge)
    redirect_uri = f"{base_url}/deviceauth/callback"
    tokens = exchange_code_for_tokens(
        base_url,
        opts.client_id,
        redirect_uri,
        pkce,
        code_resp.authorization_code,
    )
    if hasattr(tokens, "__await__"):
        tokens = await tokens
    workspace_error = ensure_workspace_allowed(opts.forced_chatgpt_workspace_id, tokens.id_token)
    if workspace_error:
        raise PermissionError(str(workspace_error))
    result = persist_tokens_async(
        opts.codex_home,
        None,
        tokens.id_token,
        tokens.access_token,
        tokens.refresh_token,
        opts.cli_auth_credentials_store_mode,
    )
    if hasattr(result, "__await__"):
        return await result
    return result


async def run_device_code_login(opts: ServerOptions, *, opener: OpenUrl = urlopen, printer: Callable[[str], None] = print) -> Any:
    device_code = request_device_code(opts, opener=opener)
    printer(print_device_code_prompt(device_code.verification_url, device_code.user_code), end="")
    return await complete_device_code_login(opts, device_code, opener=opener)


def _drain_http_error(error: HTTPError) -> None:
    fp = getattr(error, "fp", None)
    if fp is None:
        return
    closer = getattr(fp, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:
            pass
    setattr(error, "fp", None)


__all__ = [
    "ANSI_BLUE",
    "ANSI_GRAY",
    "ANSI_RESET",
    "CodeSuccessResp",
    "DEFAULT_DEVICE_AUTH_MAX_WAIT_SECONDS",
    "DEVICE_CODE_NOT_ENABLED_MESSAGE",
    "DeviceCode",
    "ServerOptions",
    "UserCodeResp",
    "complete_device_code_login",
    "deserialize_interval",
    "poll_for_token",
    "print_device_code_prompt",
    "request_device_code",
    "request_user_code",
    "run_device_code_login",
]
