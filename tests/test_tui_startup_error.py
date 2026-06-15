"""Parity tests for Rust ``codex-tui::startup_error``.

Rust source: ``codex/codex-rs/tui/src/startup_error.rs``.
"""

from pathlib import Path

from pycodex.tui.startup_error import LocalStateDbStartupError


def test_local_state_db_startup_error_accessors_and_display() -> None:
    path = Path("/tmp/state.db")
    err = LocalStateDbStartupError.new(path, "permission denied")
    assert err.state_db_path() == path
    assert err.detail() == "permission denied"
    assert str(err) == f"failed to initialize sqlite state db at {path}: permission denied"
