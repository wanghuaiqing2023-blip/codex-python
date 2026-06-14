"""Parity tests for codex-rs/tui/src/onboarding/mod.rs."""

import pycodex.tui.onboarding as onboarding
from pycodex.tui.onboarding import auth


def test_onboarding_module_reexports_auth_hyperlink_helpers():
    assert onboarding.mark_url_hyperlink is auth.mark_url_hyperlink
    assert onboarding.mark_underlined_hyperlink is auth.mark_underlined_hyperlink


def test_onboarding_module_boundary_metadata_matches_rust_module():
    assert onboarding.RUST_MODULE.crate == "codex-tui"
    assert onboarding.RUST_MODULE.module == "onboarding"
    assert onboarding.RUST_MODULE.source == "codex/codex-rs/tui/src/onboarding/mod.rs"


def test_onboarding_all_matches_rust_public_reexports_for_this_boundary():
    assert "mark_url_hyperlink" in onboarding.__all__
    assert "mark_underlined_hyperlink" in onboarding.__all__
