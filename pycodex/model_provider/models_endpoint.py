"""OpenAI-compatible ``/models`` endpoint facade."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen

from pycodex.model_provider_info import ModelProviderInfo
from pycodex.protocol import ModelsResponse

from .auth import resolve_provider_auth


MODELS_REFRESH_TIMEOUT = 5
MODELS_ENDPOINT = "models"


@dataclass
class OpenAiModelsEndpoint:
    provider_info: ModelProviderInfo
    auth_manager: Any = None

    def has_command_auth(self) -> bool:
        return self.provider_info.has_command_auth()

    async def uses_codex_backend(self) -> bool:
        auth = await self.auth()
        if auth is None:
            return False
        method = getattr(auth, "uses_codex_backend", None)
        if callable(method):
            return bool(method())
        mode = getattr(auth, "auth_mode", None)
        mode = mode() if callable(mode) else mode
        return str(getattr(mode, "value", mode)).lower() in {
            "chatgpt",
            "chatgptauthtokens",
            "chatgpt_auth_tokens",
            "agentidentity",
            "agent_identity",
        }

    async def auth(self) -> Any:
        if self.auth_manager is None:
            return None
        method = getattr(self.auth_manager, "auth", None)
        if not callable(method):
            return None
        result = method()
        if inspect.isawaitable(result):
            result = await result
        return result

    async def list_models(self, client_version: str) -> tuple[ModelsResponse, str | None]:
        auth = await self.auth()
        auth_mode = _call_optional(auth, "auth_mode")
        api_provider = self.provider_info.to_api_provider(auth_mode)
        api_auth = resolve_provider_auth(auth, self.provider_info)
        url = _append_client_version_query(_endpoint_url(api_provider.base_url), client_version)
        headers = {str(key): str(value) for key, value in dict(api_provider.headers or {}).items()}
        api_auth.add_auth_headers(headers)
        return await asyncio.to_thread(_fetch_models, url, headers)


def _fetch_models(url: str, headers: dict[str, str]) -> tuple[ModelsResponse, str | None]:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=MODELS_REFRESH_TIMEOUT) as response:
            body = response.read()
            etag = response.headers.get("ETag")
    except HTTPError as exc:
        raise OSError(f"GET /models failed with HTTP {exc.code}") from exc
    except URLError as exc:
        raise OSError(f"GET /models failed: {exc.reason}") from exc
    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"failed to decode models response: {exc}; body: {body.decode('utf-8', 'replace')}") from exc
    return ModelsResponse.from_mapping(data), etag


def _endpoint_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    path = parts.path.rstrip("/")
    if not path.endswith(f"/{MODELS_ENDPOINT}"):
        path = f"{path}/{MODELS_ENDPOINT}" if path else f"/{MODELS_ENDPOINT}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _append_client_version_query(url: str, client_version: str) -> str:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("client_version", client_version))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _call_optional(value: Any, name: str) -> Any:
    if value is None:
        return None
    method = getattr(value, name, None)
    if callable(method):
        return method()
    return method


__all__ = [
    "MODELS_ENDPOINT",
    "MODELS_REFRESH_TIMEOUT",
    "OpenAiModelsEndpoint",
]
