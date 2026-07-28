"""Streamable HTTP authentication discovery."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import ProxyHandler, Request, build_opener

from pycodex.protocol import McpAuthStatus

from .utils import build_default_headers

DISCOVERY_TIMEOUT_SECONDS = 5.0
OAUTH_DISCOVERY_HEADER = "MCP-Protocol-Version"
OAUTH_DISCOVERY_VERSION = "2024-11-05"


@dataclass(frozen=True)
class StreamableHttpOAuthDiscovery:
    scopes_supported: tuple[str, ...] | None = None


def _normalize_scopes(scopes_supported: object) -> tuple[str, ...] | None:
    if not isinstance(scopes_supported, list):
        return None
    normalized: list[str] = []
    for raw_scope in scopes_supported:
        if not isinstance(raw_scope, str):
            continue
        scope = raw_scope.strip()
        if scope and scope not in normalized:
            normalized.append(scope)
    return tuple(normalized) or None


def _discovery_paths(base_path: str) -> tuple[str, ...]:
    trimmed = base_path.strip("/")
    canonical = "/.well-known/oauth-authorization-server"
    if not trimmed:
        return (canonical,)
    candidates = (
        f"{canonical}/{trimmed}",
        f"/{trimmed}/.well-known/oauth-authorization-server",
        canonical,
    )
    return tuple(dict.fromkeys(candidates))


def _fetch_discovery(
    url: str,
    default_headers: Mapping[str, str],
) -> StreamableHttpOAuthDiscovery | None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid streamable HTTP MCP URL: {url}")
    opener = build_opener(ProxyHandler({}))
    for path in _discovery_paths(parsed.path):
        discovery_url = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
        headers = dict(default_headers)
        headers[OAUTH_DISCOVERY_HEADER] = OAUTH_DISCOVERY_VERSION
        request = Request(discovery_url, headers=headers, method="GET")
        try:
            with opener.open(request, timeout=DISCOVERY_TIMEOUT_SECONDS) as response:
                if response.status != 200:
                    continue
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        if payload.get("authorization_endpoint") and payload.get("token_endpoint"):
            return StreamableHttpOAuthDiscovery(
                scopes_supported=_normalize_scopes(payload.get("scopes_supported"))
            )
    return None


async def discover_streamable_http_oauth(
    url: str,
    http_headers: Mapping[str, str] | None = None,
    env_http_headers: Mapping[str, str] | None = None,
) -> StreamableHttpOAuthDiscovery | None:
    default_headers = build_default_headers(http_headers, env_http_headers)
    return await asyncio.to_thread(_fetch_discovery, url, default_headers)


async def supports_oauth_login(url: str) -> bool:
    return await discover_streamable_http_oauth(url) is not None


async def determine_streamable_http_auth_status(
    server_name: str,
    url: str,
    bearer_token_env_var: str | None = None,
    http_headers: Mapping[str, str] | None = None,
    env_http_headers: Mapping[str, str] | None = None,
    store_mode: object | None = None,
) -> McpAuthStatus:
    if bearer_token_env_var is not None:
        return McpAuthStatus.BEARER_TOKEN
    default_headers = build_default_headers(http_headers, env_http_headers)
    if "authorization" in default_headers:
        return McpAuthStatus.BEARER_TOKEN

    from .oauth import load_oauth_tokens

    if load_oauth_tokens(server_name, url, store_mode or "auto") is not None:
        return McpAuthStatus.OAUTH
    try:
        discovery = await asyncio.to_thread(_fetch_discovery, url, default_headers)
    except (ValueError, OSError):
        return McpAuthStatus.UNSUPPORTED
    if discovery is not None:
        return McpAuthStatus.NOT_LOGGED_IN
    return McpAuthStatus.UNSUPPORTED


__all__ = [
    "StreamableHttpOAuthDiscovery",
    "determine_streamable_http_auth_status",
    "discover_streamable_http_oauth",
    "supports_oauth_login",
]
