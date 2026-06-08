"""Rust-coordinate re-exports for ``codex-core::context::fragment``.

The implementation lives in :mod:`pycodex.core.context` because the Python port
keeps the contextual fragment hierarchy aggregated in the package root.
"""

from __future__ import annotations

from . import (
    ContextualUserFragment,
    ContextualUserFragmentBase,
    FragmentRegistration,
    FragmentRegistrationProxy,
    matches_marked_text,
)

__all__ = [
    "ContextualUserFragment",
    "ContextualUserFragmentBase",
    "FragmentRegistration",
    "FragmentRegistrationProxy",
    "matches_marked_text",
]
