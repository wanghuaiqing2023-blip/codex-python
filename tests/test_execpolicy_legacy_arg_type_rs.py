"""Rust-derived tests for ``codex-execpolicy-legacy/src/arg_type.rs``."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pycodex.execpolicy_legacy import ArgType
from pycodex.execpolicy_legacy import EmptyFileName
from pycodex.execpolicy_legacy import InvalidPositiveInteger
from pycodex.execpolicy_legacy import LiteralValueDidNotMatch
from pycodex.execpolicy_legacy import SedCommandNotProvablySafe


def test_literal_validate_matches_exact_value() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_type.rs.
    # Rust suite anchor: tests/suite/literal.rs uses ArgType::Literal for
    # subcommand matching; mismatch raises Error::LiteralValueDidNotMatch.
    arg_type = ArgType.literal("subcommand")

    assert arg_type.validate("subcommand") is None
    with pytest.raises(LiteralValueDidNotMatch) as exc_info:
        arg_type.validate("other")

    assert exc_info.value.to_mapping() == {
        "type": "LiteralValueDidNotMatch",
        "expected": "subcommand",
        "actual": "other",
    }


@pytest.mark.parametrize("factory", [ArgType.readable_file, ArgType.writeable_file])
def test_file_types_reject_empty_file_name(factory: Callable[[], ArgType]) -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_type.rs.
    # Contract: ArgType::{ReadableFile,WriteableFile} reject empty strings with
    # Error::EmptyFileName and otherwise accept the value before path checking.
    arg_type = factory()

    assert arg_type.validate("hello.txt") is None
    with pytest.raises(EmptyFileName) as exc_info:
        arg_type.validate("")

    assert exc_info.value.to_mapping() == {"type": "EmptyFileName"}


@pytest.mark.parametrize("value", ["1", "100", "18446744073709551615"])
def test_positive_integer_accepts_nonzero_u64(value: str) -> None:
    # Rust suite anchors: tests/suite/head.rs valid `head -n 100` uses
    # ArgType::PositiveInteger; Rust source accepts any nonzero u64.
    assert ArgType.positive_integer().validate(value) is None


@pytest.mark.parametrize("value", ["0", "-1", "1.0", "abc", "18446744073709551616", "１"])
def test_positive_integer_rejects_zero_and_non_u64(value: str) -> None:
    # Rust suite anchors:
    # tests/suite/head.rs::{test_head_invalid_n_as_0,
    # test_head_invalid_n_as_nonint_float,test_head_invalid_n_as_float,
    # test_head_invalid_n_as_negative_int}.
    with pytest.raises(InvalidPositiveInteger) as exc_info:
        ArgType.positive_integer().validate(value)

    assert exc_info.value.to_mapping() == {
        "type": "InvalidPositiveInteger",
        "value": value,
    }


def test_sed_command_delegates_to_sed_parser() -> None:
    # Rust crate/module: ArgType::SedCommand delegates to parse_sed_command.
    assert ArgType.sed_command().validate("122,202p") is None
    with pytest.raises(SedCommandNotProvablySafe):
        ArgType.sed_command().validate("s/y/echo hi/e")


def test_opaque_unknown_and_write_detection_match_rust() -> None:
    # Rust crate/module: ArgType::might_write_file.
    assert ArgType.opaque_non_file().validate("") is None
    assert ArgType.unknown().validate("") is None

    assert ArgType.writeable_file().might_write_file() is True
    assert ArgType.unknown().might_write_file() is True
    assert ArgType.literal("x").might_write_file() is False
    assert ArgType.opaque_non_file().might_write_file() is False
    assert ArgType.positive_integer().might_write_file() is False
    assert ArgType.readable_file().might_write_file() is False
    assert ArgType.sed_command().might_write_file() is False
