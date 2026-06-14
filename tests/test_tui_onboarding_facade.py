"""Parity tests for Rust ``codex-tui::onboarding`` facade.

Rust source: ``codex/codex-rs/tui/src/onboarding/mod.rs``.
"""

from pycodex.tui import onboarding
from pycodex.tui.onboarding import auth


def test_onboarding_parent_facade_reexports_auth_helpers() -> None:
    """Rust ``mod.rs`` declares child modules and re-exports auth hyperlink helpers."""

    assert onboarding.RUST_MODULE.module == "onboarding"
    assert onboarding.RUST_MODULE.source == "codex/codex-rs/tui/src/onboarding/mod.rs"
    assert onboarding.ONBOARDING_SUBMODULES == (
        "auth",
        "keys",
        "onboarding_screen",
        "trust_directory",
        "welcome",
    )

    assert onboarding.mark_url_hyperlink is auth.mark_url_hyperlink
    assert onboarding.mark_underlined_hyperlink is auth.mark_underlined_hyperlink
