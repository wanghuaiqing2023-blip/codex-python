"""Parity tests for Rust ``codex-tui::startup_error``.

Rust source: ``codex/codex-rs/tui/src/startup_error.rs``.
"""

from pathlib import Path

from pycodex.tui.startup_error import LocalStateDbStartupError


def test_local_state_db_startup_error_accessors_and_display() -> None:
    err = LocalStateDbStartupError.new(Path("/tmp/state.db"), "permission denied")
    assert err.state_db_path() == Path("/tmp/state.db")
    assert err.detail() == "permission denied"
    assert str(err) == "failed to initialize sqlite state db at /tmp/state.db: permission denied"
