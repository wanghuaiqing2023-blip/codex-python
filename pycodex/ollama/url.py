"""URL helpers for Rust ``codex-ollama/src/url.rs``."""

from __future__ import annotations


def is_openai_compatible_base_url(base_url: str) -> bool:
    """Return whether ``base_url`` points at an OpenAI-compatible ``/v1`` root."""

    return str(base_url).rstrip("/").endswith("/v1")


def base_url_to_host_root(base_url: str) -> str:
    """Convert an Ollama provider base URL into the native host root."""

    trimmed = str(base_url).rstrip("/")
    if trimmed.endswith("/v1"):
        return trimmed[: -len("/v1")].rstrip("/")
    return trimmed


__all__ = ["base_url_to_host_root", "is_openai_compatible_base_url"]
