"""Semantic package boundary for codex-rs/tui/src/onboarding/mod.rs.

The Rust module declares onboarding submodules and re-exports two hyperlink
helpers from ``onboarding::auth``.  Python mirrors that package-level export
without claiming the full ``onboarding::auth`` behavior is complete.
"""

from __future__ import annotations

from .._porting import RustTuiModule
from .auth import mark_underlined_hyperlink, mark_url_hyperlink


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="onboarding",
    source="codex/codex-rs/tui/src/onboarding/mod.rs",
)

ONBOARDING_SUBMODULES = (
    "auth",
    "keys",
    "onboarding_screen",
    "trust_directory",
    "welcome",
)


__all__ = [
    "ONBOARDING_SUBMODULES",
    "RUST_MODULE",
    "mark_underlined_hyperlink",
    "mark_url_hyperlink",
]
