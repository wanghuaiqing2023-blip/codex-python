"""Process-wide rustls crypto provider initialization facade.

Rust installs the ring rustls crypto provider exactly once. Python has no
rustls global provider, so this module preserves the idempotent process-wide
initialization boundary and allows an explicit installer to be injected by any
runtime that actually binds rustls.
"""

from __future__ import annotations

from threading import Lock
from typing import Callable

_INSTALLED = False
_LOCK = Lock()


def ensure_rustls_crypto_provider(installer: Callable[[], object] | None = None) -> None:
    """Ensure the process-wide rustls crypto provider is installed once."""

    global _INSTALLED
    if _INSTALLED:
        return
    with _LOCK:
        if _INSTALLED:
            return
        if installer is not None:
            installer()
        _INSTALLED = True


def rustls_crypto_provider_installed() -> bool:
    return _INSTALLED


def reset_rustls_crypto_provider_for_tests() -> None:
    global _INSTALLED
    with _LOCK:
        _INSTALLED = False


__all__ = [
    "ensure_rustls_crypto_provider",
    "reset_rustls_crypto_provider_for_tests",
    "rustls_crypto_provider_installed",
]
