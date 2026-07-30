"""Authenticated ChatGPT backend GET requests owned by ``chatgpt_client.rs``."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pycodex.login.auth.manager import AuthManager
from pycodex.model_provider.auth import auth_provider_from_auth

OAI_PRODUCT_SKU_HEADER = "OAI-Product-Sku"
CODEX_PRODUCT_SKU = "codex"


async def chatgpt_get_request(config: Any, path: str) -> Any:
    return await chatgpt_get_request_with_timeout(config, path, None)


async def chatgpt_get_request_with_timeout(
    config: Any,
    path: str,
    timeout: float | None = None,
) -> Any:
    auth_manager = await _auth_manager_from_config(config)
    auth = await auth_manager.auth()
    if auth is None:
        raise RuntimeError("ChatGPT auth not available")
    if not auth.uses_codex_backend():
        raise RuntimeError("ChatGPT backend requests require Codex backend auth")
    if auth.get_account_id() is None:
        raise RuntimeError("ChatGPT account ID not available, please re-run `codex login`")

    base_url = str(getattr(config, "chatgpt_base_url")).rstrip("/")
    url = f"{base_url}/{str(path).lstrip('/')}"
    headers = {
        str(key): str(value)
        for key, value in auth_provider_from_auth(auth).to_auth_headers().items()
    }
    headers[OAI_PRODUCT_SKU_HEADER] = CODEX_PRODUCT_SKU
    headers["Content-Type"] = "application/json"
    return await _send_get_json(url, headers, timeout)


async def _auth_manager_from_config(config: Any) -> AuthManager:
    manager = await AuthManager.new(
        getattr(config, "codex_home"),
        False,
        str(getattr(config, "auth_credentials_store_mode", "file")),
        getattr(config, "chatgpt_base_url", None),
    )
    manager.set_forced_chatgpt_workspace_id(
        getattr(config, "forced_chatgpt_workspace_id", None)
    )
    return manager


async def _send_get_json(
    url: str,
    headers: Mapping[str, str],
    timeout: float | None,
) -> Any:
    return await asyncio.to_thread(_send_get_json_blocking, url, dict(headers), timeout)


def _send_get_json_blocking(
    url: str,
    headers: dict[str, str],
    timeout: float | None,
) -> Any:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
            body = response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Request failed with status {exc.code}: {body}") from exc
    except (OSError, URLError) as exc:
        raise RuntimeError(f"Failed to send request: {exc}") from exc

    if not 200 <= status < 300:
        raise RuntimeError(
            f"Request failed with status {status}: "
            f"{body.decode('utf-8', errors='replace')}"
        )
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to parse JSON response: {exc}") from exc


__all__ = [
    "CODEX_PRODUCT_SKU",
    "OAI_PRODUCT_SKU_HEADER",
    "chatgpt_get_request",
    "chatgpt_get_request_with_timeout",
]
