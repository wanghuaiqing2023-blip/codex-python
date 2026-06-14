"""Parity tests for codex-rs/tui/src/public_widgets/mod.rs."""

import importlib

from pycodex.tui import public_widgets


def test_public_widgets_module_boundary_metadata_matches_rust_mod():
    assert public_widgets.RUST_MODULE.crate == "codex-tui"
    assert public_widgets.RUST_MODULE.module == "public_widgets"
    assert public_widgets.RUST_MODULE.source == "codex/codex-rs/tui/src/public_widgets/mod.rs"


def test_public_widgets_declares_composer_input_submodule_boundary():
    assert public_widgets.PUBLIC_WIDGET_SUBMODULES == ("composer_input",)
    assert importlib.import_module("pycodex.tui.public_widgets.composer_input") is not None


def test_public_widgets_all_is_package_boundary_only():
    assert set(public_widgets.__all__) == {"PUBLIC_WIDGET_SUBMODULES", "RUST_MODULE"}
