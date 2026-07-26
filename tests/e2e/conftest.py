"""Shared pytest configuration for opt-in end-to-end scenarios."""

from __future__ import annotations

# Environment gates remain scenario-owned so collection never starts native
# Codex processes unless the caller explicitly enables the corresponding tier.
