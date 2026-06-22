"""Parity tests for Rust ``codex-file-search/src/cli.rs``.

Pytest is deferred until the full ``codex-file-search`` crate is functionally
complete.
"""

from pathlib import Path

import pytest

from pycodex.file_search import Cli


def test_cli_defaults_match_rust_clap_defaults() -> None:
    """Rust: ``Cli`` field defaults from clap attributes."""

    cli = Cli.parse_args([])

    assert cli.json is False
    assert cli.limit == 64
    assert cli.cwd is None
    assert cli.compute_indices is False
    assert cli.threads == 2
    assert cli.exclude == []
    assert cli.pattern is None


def test_cli_parses_short_and_long_options() -> None:
    """Rust: ``Cli`` parser accepts short aliases and append excludes."""

    cli = Cli.parse_args(
        [
            "--json",
            "-l",
            "7",
            "-C",
            "workspace",
            "--compute-indices",
            "--threads",
            "3",
            "-e",
            "*.tmp",
            "--exclude",
            "target",
            "needle",
        ]
    )

    assert cli.json is True
    assert cli.limit == 7
    assert cli.cwd == Path("workspace")
    assert cli.compute_indices is True
    assert cli.threads == 3
    assert cli.exclude == ["*.tmp", "target"]
    assert cli.pattern == "needle"


def test_cli_rejects_zero_limit_and_threads() -> None:
    """Rust: ``NonZero<usize>`` rejects zero values."""

    with pytest.raises(SystemExit):
        Cli.parse_args(["--limit", "0"])
    with pytest.raises(SystemExit):
        Cli.parse_args(["--threads", "0"])
    with pytest.raises(ValueError, match="limit must be non-zero"):
        Cli(limit=0)
    with pytest.raises(ValueError, match="threads must be non-zero"):
        Cli(threads=0)

