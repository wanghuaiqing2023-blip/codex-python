"""Ollama HTTP client for Rust ``codex-ollama/src/client.rs``."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import logging
from typing import Any, Protocol
import urllib.error
import urllib.request

from pycodex.model_provider_info import OLLAMA_OSS_PROVIDER_ID

from .parser import pull_events_from_value
from .pull import Error, PullEvent, PullProgressReporter, Status, Success
from .url import base_url_to_host_root, is_openai_compatible_base_url


OLLAMA_CONNECTION_ERROR = (
    "No running Ollama server detected. Start it with: `ollama serve` "
    "(after installing). Install instructions: "
    "https://github.com/ollama/ollama?tab=readme-ov-file#ollama"
)


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "Version":
        parts = value.split(".")
        if len(parts) != 3:
            raise ValueError(f"invalid semantic version: {value}")
        try:
            major, minor, patch = (int(part) for part in parts)
        except ValueError as exc:
            raise ValueError(f"invalid semantic version: {value}") from exc
        if major < 0 or minor < 0 or patch < 0:
            raise ValueError(f"invalid semantic version: {value}")
        return cls(major=major, minor=minor, patch=patch)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes = b""

    def is_success(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class OllamaTransport(Protocol):
    def request(self, method: str, url: str, payload: Mapping[str, Any] | None = None) -> HttpResponse:
        """Perform one HTTP request."""

    def stream(self, method: str, url: str, payload: Mapping[str, Any] | None = None) -> Iterable[bytes]:
        """Perform one streaming HTTP request and yield byte chunks."""


class UrllibOllamaTransport:
    def __init__(self, timeout: float = 5.0) -> None:
        self.timeout = timeout

    def request(self, method: str, url: str, payload: Mapping[str, Any] | None = None) -> HttpResponse:
        req = self._request(method, url, payload)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return HttpResponse(status=response.status, body=response.read())
        except urllib.error.HTTPError as exc:
            return HttpResponse(status=exc.code, body=exc.read())

    def stream(self, method: str, url: str, payload: Mapping[str, Any] | None = None) -> Iterable[bytes]:
        req = self._request(method, url, payload)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                status = response.status
                if not 200 <= status < 300:
                    raise OSError(f"failed to start pull: HTTP {status}")
                while True:
                    chunk = response.readline()
                    if not chunk:
                        break
                    yield chunk
        except urllib.error.HTTPError as exc:
            raise OSError(f"failed to start pull: HTTP {exc.code}") from exc

    @staticmethod
    def _request(method: str, url: str, payload: Mapping[str, Any] | None) -> urllib.request.Request:
        body = json.dumps(dict(payload)).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        return urllib.request.Request(url, data=body, method=method, headers=headers)


@dataclass
class OllamaClient:
    host_root: str
    uses_openai_compat: bool = False
    transport: OllamaTransport | None = None
    timeout: float = 5.0

    @classmethod
    async def try_from_oss_provider(cls, config: Any) -> "OllamaClient":
        providers = _field(config, "model_providers", {})
        if not isinstance(providers, Mapping) or OLLAMA_OSS_PROVIDER_ID not in providers:
            raise FileNotFoundError(f"Built-in provider {OLLAMA_OSS_PROVIDER_ID} not found")
        return await cls.try_from_provider(providers[OLLAMA_OSS_PROVIDER_ID])

    @classmethod
    async def try_from_provider(cls, provider: Any, *, transport: OllamaTransport | None = None) -> "OllamaClient":
        base_url = _field(provider, "base_url")
        if base_url is None:
            raise ValueError("oss provider must have a base_url")
        client = cls(
            host_root=base_url_to_host_root(str(base_url)),
            uses_openai_compat=is_openai_compatible_base_url(str(base_url)),
            transport=transport,
        )
        await client.probe_server()
        return client

    @classmethod
    async def try_from_provider_with_base_url(
        cls,
        base_url: str,
        *,
        transport: OllamaTransport | None = None,
    ) -> "OllamaClient":
        client = cls(
            host_root=base_url_to_host_root(str(base_url)),
            uses_openai_compat=is_openai_compatible_base_url(str(base_url)),
            transport=transport,
        )
        await client.probe_server()
        return client

    @classmethod
    def from_host_root(cls, host_root: str, *, transport: OllamaTransport | None = None) -> "OllamaClient":
        return cls(host_root=str(host_root), uses_openai_compat=False, transport=transport)

    @property
    def _transport(self) -> OllamaTransport:
        if self.transport is None:
            self.transport = UrllibOllamaTransport(timeout=self.timeout)
        return self.transport

    async def probe_server(self) -> None:
        url = (
            f"{self.host_root.rstrip('/')}/v1/models"
            if self.uses_openai_compat
            else f"{self.host_root.rstrip('/')}/api/tags"
        )

        def request() -> None:
            try:
                response = self._transport.request("GET", url)
            except OSError as exc:
                logging.getLogger(__name__).warning("Failed to connect to Ollama server: %r", exc)
                raise OSError(OLLAMA_CONNECTION_ERROR) from exc
            if response.is_success():
                return
            logging.getLogger(__name__).warning(
                "Failed to probe server at %s: HTTP %s",
                self.host_root,
                response.status,
            )
            raise OSError(OLLAMA_CONNECTION_ERROR)

        await asyncio.to_thread(request)

    async def fetch_models(self) -> list[str]:
        url = f"{self.host_root.rstrip('/')}/api/tags"

        def request() -> list[str]:
            response = self._transport.request("GET", url)
            if not response.is_success():
                return []
            payload = response.json()
            models = payload.get("models") if isinstance(payload, Mapping) else None
            if not isinstance(models, list):
                return []
            return [
                str(model["name"])
                for model in models
                if isinstance(model, Mapping) and isinstance(model.get("name"), str)
            ]

        return await asyncio.to_thread(request)

    async def fetch_version(self) -> Version | None:
        url = f"{self.host_root.rstrip('/')}/api/version"

        def request() -> Version | None:
            response = self._transport.request("GET", url)
            if not response.is_success():
                return None
            payload = response.json()
            version_value = payload.get("version") if isinstance(payload, Mapping) else None
            if not isinstance(version_value, str):
                return None
            version_str = version_value.strip()
            normalized = version_str.lstrip("v")
            try:
                return Version.parse(normalized)
            except ValueError as exc:
                logging.getLogger(__name__).warning(
                    "Failed to parse Ollama version `%s`: %s",
                    version_str,
                    exc,
                )
                return None

        return await asyncio.to_thread(request)

    async def pull_model_stream(self, model: str):
        url = f"{self.host_root.rstrip('/')}/api/pull"

        def collect() -> list[PullEvent]:
            events: list[PullEvent] = []
            buffer = b""
            for chunk in self._transport.stream("POST", url, {"model": model, "stream": True}):
                buffer += bytes(chunk)
                while b"\n" in buffer:
                    raw_line, buffer = buffer.split(b"\n", 1)
                    _append_pull_events_from_line(raw_line, events)
                    if events and isinstance(events[-1], Error):
                        return events
                    if events and isinstance(events[-1], Success):
                        return events
            return events

        for event in await asyncio.to_thread(collect):
            yield event

    async def pull_with_reporter(self, model: str, reporter: PullProgressReporter) -> None:
        reporter.on_event(Status(f"Pulling model {model}..."))
        async for event in self.pull_model_stream(model):
            reporter.on_event(event)
            if isinstance(event, Success):
                return
            if isinstance(event, Error):
                raise OSError(f"Pull failed: {event.message}")
        raise OSError("Pull stream ended unexpectedly without success.")


def _append_pull_events_from_line(raw_line: bytes, events: list[PullEvent]) -> None:
    try:
        text = raw_line.decode("utf-8").strip()
    except UnicodeDecodeError:
        return
    if not text:
        return
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return
    if not isinstance(value, Mapping):
        return
    events.extend(pull_events_from_value(value))
    error = value.get("error")
    if isinstance(error, str):
        events.append(Error(error))
        return
    status = value.get("status")
    if isinstance(status, str) and status == "success":
        events.append(Success())


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


__all__ = [
    "HttpResponse",
    "OLLAMA_CONNECTION_ERROR",
    "OllamaClient",
    "OllamaTransport",
    "UrllibOllamaTransport",
    "Version",
]
