"""Python port surface for Rust ``codex-secrets``."""

from __future__ import annotations

from .sanitizer import redact_secrets


__all__ = [
    "redact_secrets",
]
