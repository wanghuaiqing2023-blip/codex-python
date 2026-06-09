"""OSS provider utilities shared by CLI/TUI/exec paths."""

from __future__ import annotations

import inspect
from typing import Any, Mapping

LMSTUDIO_OSS_PROVIDER_ID = "lmstudio"
OLLAMA_OSS_PROVIDER_ID = "ollama"
LMSTUDIO_DEFAULT_OSS_MODEL = "openai/gpt-oss-20b"
OLLAMA_DEFAULT_OSS_MODEL = "gpt-oss:20b"


def get_default_model_for_oss_provider(provider_id: str) -> str | None:
    if not isinstance(provider_id, str):
        raise TypeError("provider_id must be a string")
    if provider_id == LMSTUDIO_OSS_PROVIDER_ID:
        return LMSTUDIO_DEFAULT_OSS_MODEL
    if provider_id == OLLAMA_OSS_PROVIDER_ID:
        return OLLAMA_DEFAULT_OSS_MODEL
    return None


async def ensure_oss_provider_ready(
    provider_id: str,
    config: Any,
    backends: Mapping[str, Any] | None = None,
) -> None:
    """Ensure an OSS provider is ready, delegating to explicit backends.

    Unknown providers are skipped, matching Rust. Known providers require an
    injected backend that exposes the Rust-shaped readiness methods; this avoids
    silently simulating local LM Studio/Ollama setup.
    """

    if not isinstance(provider_id, str):
        raise TypeError("provider_id must be a string")
    if provider_id not in {LMSTUDIO_OSS_PROVIDER_ID, OLLAMA_OSS_PROVIDER_ID}:
        return
    backend = (backends or {}).get(provider_id)
    if backend is None:
        raise NotImplementedError(f"OSS readiness backend required for provider {provider_id}")
    if provider_id == OLLAMA_OSS_PROVIDER_ID:
        ensure_responses_supported = getattr(backend, "ensure_responses_supported", None)
        if ensure_responses_supported is None:
            raise NotImplementedError("ollama backend must expose ensure_responses_supported")
        await _maybe_await(ensure_responses_supported(getattr(config, "model_provider", None)))
    ensure_oss_ready = getattr(backend, "ensure_oss_ready", None)
    if ensure_oss_ready is None:
        raise NotImplementedError(f"{provider_id} backend must expose ensure_oss_ready")
    try:
        await _maybe_await(ensure_oss_ready(config))
    except Exception as exc:  # noqa: BLE001 - preserve Rust io::Error::other wording.
        raise OSError(f"OSS setup failed: {exc}") from exc


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "LMSTUDIO_DEFAULT_OSS_MODEL",
    "LMSTUDIO_OSS_PROVIDER_ID",
    "OLLAMA_DEFAULT_OSS_MODEL",
    "OLLAMA_OSS_PROVIDER_ID",
    "ensure_oss_provider_ready",
    "get_default_model_for_oss_provider",
]
