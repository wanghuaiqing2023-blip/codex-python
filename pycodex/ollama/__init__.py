"""Python port surface for Rust ``codex-ollama``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import Any

from .client import OLLAMA_CONNECTION_ERROR, HttpResponse, OllamaClient, OllamaTransport, Version
from .parser import pull_events_from_value
from .pull import (
    ChunkProgress,
    CliProgressReporter,
    Error,
    PullEvent,
    PullProgressReporter,
    Status,
    Success,
    TuiProgressReporter,
)
from .url import base_url_to_host_root, is_openai_compatible_base_url


DEFAULT_OSS_MODEL = "gpt-oss:20b"


def min_responses_version() -> Version:
    return Version(0, 13, 4)


def supports_responses(version: Version) -> bool:
    return version == Version(0, 0, 0) or version >= min_responses_version()


async def ensure_oss_ready(
    config: Any,
    *,
    client_factory: Callable[[Any], Awaitable[OllamaClient]] | None = None,
    reporter_factory: Callable[[], PullProgressReporter] | None = None,
) -> None:
    """Prepare the local Ollama OSS environment, mirroring Rust ``ensure_oss_ready``."""

    model = _config_model(config) or DEFAULT_OSS_MODEL
    factory = client_factory or OllamaClient.try_from_oss_provider
    client = await factory(config)

    try:
        models = await client.fetch_models()
    except Exception as exc:  # noqa: BLE001 - Rust logs and continues.
        logging.getLogger(__name__).warning("Failed to query local models from Ollama: %s.", exc)
        return

    if model not in models:
        make_reporter = reporter_factory or CliProgressReporter
        await client.pull_with_reporter(model, make_reporter())


async def ensure_responses_supported(
    provider: Any,
    *,
    client_factory: Callable[[Any], Awaitable[OllamaClient]] | None = None,
) -> None:
    """Ensure the running Ollama server is new enough for the Responses API."""

    factory = client_factory or OllamaClient.try_from_provider
    client = await factory(provider)
    version = await client.fetch_version()
    if version is None:
        return
    if supports_responses(version):
        return
    minimum = min_responses_version()
    raise OSError(f"Ollama {version} is too old. Codex requires Ollama {minimum} or newer.")


def _config_model(config: Any) -> str | None:
    if isinstance(config, dict):
        value = config.get("model")
    else:
        value = getattr(config, "model", None)
    return value if isinstance(value, str) and value else None


__all__ = [
    "ChunkProgress",
    "CliProgressReporter",
    "DEFAULT_OSS_MODEL",
    "Error",
    "HttpResponse",
    "OLLAMA_CONNECTION_ERROR",
    "OllamaClient",
    "OllamaTransport",
    "PullEvent",
    "PullProgressReporter",
    "Status",
    "Success",
    "TuiProgressReporter",
    "Version",
    "base_url_to_host_root",
    "ensure_oss_ready",
    "ensure_responses_supported",
    "is_openai_compatible_base_url",
    "min_responses_version",
    "pull_events_from_value",
    "supports_responses",
]
