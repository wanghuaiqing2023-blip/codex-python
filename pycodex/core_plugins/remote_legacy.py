"""Legacy remote plugin API.

Rust owner: ``codex-core-plugins::remote_legacy``.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from .remote import RemotePluginServiceConfig

DEFAULT_REMOTE_MARKETPLACE_NAME = "openai-curated"
REMOTE_PLUGIN_FETCH_TIMEOUT = 30
REMOTE_FEATURED_PLUGIN_FETCH_TIMEOUT = 10
REMOTE_PLUGIN_MUTATION_TIMEOUT = 30


@dataclass(frozen=True)
class RemotePluginStatusSummary:
    name: str
    marketplace_name: str = DEFAULT_REMOTE_MARKETPLACE_NAME
    enabled: bool = False

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "RemotePluginStatusSummary":
        return cls(
            name=str(value["name"]),
            marketplace_name=str(
                value.get("marketplace_name", DEFAULT_REMOTE_MARKETPLACE_NAME)
            ),
            enabled=bool(value.get("enabled", False)),
        )


class RemotePluginMutationError(RuntimeError):
    pass


class RemotePluginFetchError(RuntimeError):
    pass


async def fetch_remote_plugin_status(
    config: RemotePluginServiceConfig,
    auth: Any | None,
    *,
    transport: Any | None = None,
) -> list[RemotePluginStatusSummary]:
    _ensure_backend_auth(auth, RemotePluginFetchError)
    url = f"{config.chatgpt_base_url.rstrip('/')}/plugins/list"
    payload = await _request_json(
        "GET",
        url,
        auth,
        REMOTE_PLUGIN_FETCH_TIMEOUT,
        transport=transport,
    )
    if not isinstance(payload, list):
        raise RemotePluginFetchError("remote plugin status response must be an array")
    return [
        RemotePluginStatusSummary.from_mapping(item)
        for item in payload
        if isinstance(item, dict)
    ]


async def fetch_remote_featured_plugin_ids(
    config: RemotePluginServiceConfig,
    auth: Any | None,
    product: Any | None = None,
    *,
    transport: Any | None = None,
) -> list[str]:
    platform = _product_platform(product)
    url = (
        f"{config.chatgpt_base_url.rstrip('/')}/plugins/featured?"
        f"{urlencode({'platform': platform})}"
    )
    payload = await _request_json(
        "GET",
        url,
        auth if _uses_backend(auth) else None,
        REMOTE_FEATURED_PLUGIN_FETCH_TIMEOUT,
        transport=transport,
    )
    if not isinstance(payload, list):
        raise RemotePluginFetchError("featured plugin response must be an array")
    return [str(value) for value in payload]


async def enable_remote_plugin(
    config: RemotePluginServiceConfig,
    auth: Any | None,
    plugin_id: str,
    *,
    transport: Any | None = None,
) -> None:
    await _post_remote_plugin_mutation(
        config,
        auth,
        plugin_id,
        "enable",
        transport=transport,
    )


async def uninstall_remote_plugin(
    config: RemotePluginServiceConfig,
    auth: Any | None,
    plugin_id: str,
    *,
    transport: Any | None = None,
) -> None:
    await _post_remote_plugin_mutation(
        config,
        auth,
        plugin_id,
        "uninstall",
        transport=transport,
    )


def remote_plugin_mutation_url(
    config: RemotePluginServiceConfig,
    plugin_id: str,
    action: str,
) -> str:
    parsed = urlsplit(config.chatgpt_base_url.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RemotePluginMutationError(
            "chatgpt base url cannot be used for plugin mutation"
        )
    path = "/".join(
        [
            parsed.path.rstrip("/"),
            "plugins",
            quote(plugin_id, safe=""),
            quote(action, safe=""),
        ]
    )
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


async def _post_remote_plugin_mutation(
    config: RemotePluginServiceConfig,
    auth: Any | None,
    plugin_id: str,
    action: str,
    *,
    transport: Any | None,
) -> dict[str, Any]:
    _ensure_backend_auth(auth, RemotePluginMutationError)
    url = remote_plugin_mutation_url(config, plugin_id, action)
    payload = await _request_json(
        "POST",
        url,
        auth,
        REMOTE_PLUGIN_MUTATION_TIMEOUT,
        transport=transport,
    )
    if not isinstance(payload, dict):
        raise RemotePluginMutationError("remote plugin mutation response must be an object")
    actual_id = str(payload.get("id", ""))
    actual_enabled = bool(payload.get("enabled", False))
    expected_enabled = action == "enable"
    if actual_id != plugin_id:
        raise RemotePluginMutationError(
            f"remote plugin mutation returned unexpected plugin id: expected "
            f"`{plugin_id}`, got `{actual_id}`"
        )
    if actual_enabled != expected_enabled:
        raise RemotePluginMutationError(
            f"remote plugin mutation returned unexpected enabled state for "
            f"`{plugin_id}`: expected {expected_enabled}, got {actual_enabled}"
        )
    return payload


async def _request_json(
    method: str,
    url: str,
    auth: Any | None,
    timeout: int,
    *,
    transport: Any | None,
) -> Any:
    headers = _auth_headers(auth)
    if transport is not None:
        response = await transport.request(
            method,
            url,
            headers=headers,
            timeout=timeout,
        )
        status = int(getattr(response, "status", getattr(response, "status_code", 200)))
        body = await _response_text(response)
    else:
        status, body = await asyncio.to_thread(
            _urllib_request,
            method,
            url,
            headers,
            timeout,
        )
    if not 200 <= status < 300:
        raise RemotePluginFetchError(
            f"remote plugin request to {url} failed with status {status}: {body}"
        )
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RemotePluginFetchError(
            f"failed to parse remote plugin response from {url}: {exc}"
        ) from exc


def _urllib_request(
    method: str,
    url: str,
    headers: dict[str, str],
    timeout: int,
) -> tuple[int, str]:
    request = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def _ensure_backend_auth(auth: Any | None, error_type: type[RuntimeError]) -> None:
    if auth is None:
        raise error_type("chatgpt authentication required")
    if not _uses_backend(auth):
        raise error_type(
            "chatgpt authentication required; api key auth is not supported"
        )


def _uses_backend(auth: Any | None) -> bool:
    method = getattr(auth, "uses_codex_backend", None)
    return bool(method()) if callable(method) else False


def _auth_headers(auth: Any | None) -> dict[str, str]:
    if auth is None:
        return {}
    headers: dict[str, str] = {}
    token_getter = getattr(auth, "get_token", None)
    if callable(token_getter):
        token = token_getter()
        if token:
            headers["authorization"] = f"Bearer {token}"
    account_getter = getattr(auth, "get_account_id", None)
    if callable(account_getter):
        account_id = account_getter()
        if account_id:
            headers["chatgpt-account-id"] = str(account_id)
    return headers


def _product_platform(product: Any | None) -> str:
    if product is None:
        return "codex"
    method = getattr(product, "to_app_platform", None)
    if callable(method):
        return str(method())
    return str(getattr(product, "value", product)).lower()


async def _response_text(response: Any) -> str:
    text = getattr(response, "text", "")
    if callable(text):
        text = text()
    if hasattr(text, "__await__"):
        text = await text
    return str(text)


__all__ = [
    "DEFAULT_REMOTE_MARKETPLACE_NAME",
    "RemotePluginFetchError",
    "RemotePluginMutationError",
    "RemotePluginStatusSummary",
    "enable_remote_plugin",
    "fetch_remote_featured_plugin_ids",
    "fetch_remote_plugin_status",
    "remote_plugin_mutation_url",
    "uninstall_remote_plugin",
]
