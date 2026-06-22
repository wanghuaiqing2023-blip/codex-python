"""Provider contracts for the Rust ``codex-api`` port.

Rust source:
- ``codex/codex-rs/codex-api/src/provider.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from pycodex.codex_client import Request
from pycodex.codex_client import RequestCompression
from pycodex.codex_client import RetryOn
from pycodex.codex_client import RetryPolicy


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int
    base_delay: float
    retry_429: bool
    retry_5xx: bool
    retry_transport: bool

    def to_policy(self) -> RetryPolicy:
        return RetryPolicy(
            max_attempts=self.max_attempts,
            base_delay=self.base_delay,
            retry_on=RetryOn(
                retry_429=self.retry_429,
                retry_5xx=self.retry_5xx,
                retry_transport=self.retry_transport,
            ),
        )


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    query_params: Mapping[str, str] | None
    headers: Mapping[str, str]
    retry: RetryConfig
    stream_idle_timeout: float

    def url_for_path(self, path: str) -> str:
        base = self.base_url.rstrip("/")
        normalized_path = path.lstrip("/")
        if normalized_path:
            url = f"{base}/{normalized_path}"
        else:
            url = base

        if self.query_params:
            query = "&".join(f"{key}={value}" for key, value in self.query_params.items())
            if query:
                url += "?" + query
        return url

    def build_request(self, method: str, path: str) -> Request:
        return Request(
            method=method,
            url=self.url_for_path(path),
            headers=dict(self.headers),
            body=None,
            compression=RequestCompression.NONE,
            timeout=None,
        )

    def is_azure_responses_endpoint(self) -> bool:
        return is_azure_responses_provider(self.name, self.base_url)

    def websocket_url_for_path(self, path: str) -> str:
        url = self.url_for_path(path)
        parts = urlsplit(url)
        if parts.scheme == "http":
            return urlunsplit(("ws", parts.netloc, parts.path, parts.query, parts.fragment))
        if parts.scheme == "https":
            return urlunsplit(("wss", parts.netloc, parts.path, parts.query, parts.fragment))
        return url


def is_azure_responses_provider(name: str, base_url: str | None = None) -> bool:
    if name.lower() == "azure":
        return True
    if base_url is None:
        return False
    return _matches_azure_responses_base_url(base_url)


def _matches_azure_responses_base_url(base_url: str) -> bool:
    lower = base_url.lower()
    azure_markers = (
        "openai.azure.",
        "cognitiveservices.azure.",
        "aoai.azure.",
        "azure-api.",
        "azurefd.",
        "windows.net/openai",
    )
    return any(marker in lower for marker in azure_markers)
