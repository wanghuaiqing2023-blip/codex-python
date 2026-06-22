"""Rust-derived tests for ``codex-execpolicy-legacy/src/sed_command.rs``."""

from __future__ import annotations

import pytest

from pycodex.execpolicy_legacy import SedCommandNotProvablySafe
from pycodex.execpolicy_legacy import parse_sed_command


def test_parses_simple_print_command() -> None:
    # Rust crate/module/test:
    # codex-execpolicy-legacy/src/sed_command.rs
    # tests/suite/parse_sed_command.rs::parses_simple_print_command.
    assert parse_sed_command("122,202p") is None


@pytest.mark.parametrize("command", ["122,202", "122202", "s/y/echo hi/e"])
def test_rejects_malformed_or_dangerous_commands(command: str) -> None:
    # Rust crate/module/tests:
    # tests/suite/parse_sed_command.rs::rejects_malformed_print_command
    # tests/suite/sed.rs::test_sed_reject_dangerous_command.
    with pytest.raises(SedCommandNotProvablySafe) as exc_info:
        parse_sed_command(command)

    assert exc_info.value.command == command
    assert exc_info.value.to_mapping() == {
        "type": "SedCommandNotProvablySafe",
        "command": command,
    }


@pytest.mark.parametrize(
    "command",
    [
        "0,0p",
        "18446744073709551615,18446744073709551615p",
    ],
)
def test_accepts_unsigned_64_bit_bounds(command: str) -> None:
    # Rust source contract: both bounds are accepted when Rust
    # `str::parse::<u64>()` succeeds.
    assert parse_sed_command(command) is None


@pytest.mark.parametrize(
    "command",
    [
        "-1,2p",
        "1,-2p",
        "1.0,2p",
        "1,2.0p",
        "18446744073709551616,2p",
        "１,2p",
    ],
)
def test_rejects_values_that_do_not_parse_as_rust_u64(command: str) -> None:
    # Rust source contract: `str::parse::<u64>()` rejects signs, floats,
    # overflow, and non-ASCII decimal forms.
    with pytest.raises(SedCommandNotProvablySafe):
        parse_sed_command(command)
