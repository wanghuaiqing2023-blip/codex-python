"""Rust-derived tests for ``codex-execpolicy-legacy/src/arg_resolver.rs``."""

from __future__ import annotations

import pytest

from pycodex.execpolicy_legacy import ArgMatcher
from pycodex.execpolicy_legacy import ArgType
from pycodex.execpolicy_legacy import LiteralValueDidNotMatch
from pycodex.execpolicy_legacy import MatchedArg
from pycodex.execpolicy_legacy import MultipleVarargPatterns
from pycodex.execpolicy_legacy import NotEnoughArgs
from pycodex.execpolicy_legacy import PositionalArg
from pycodex.execpolicy_legacy import RangeEndOutOfBounds
from pycodex.execpolicy_legacy import UnexpectedArguments
from pycodex.execpolicy_legacy import VarargMatcherDidNotMatchAnything
from pycodex.execpolicy_legacy import resolve_observed_args_with_patterns


def _args(*values: str) -> list[PositionalArg]:
    return [PositionalArg(index=index, value=value) for index, value in enumerate(values)]


def test_resolves_vararg_prefix_and_suffix_like_cp() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_resolver.rs.
    # Rust suite anchor: tests/suite/cp.rs::test_cp_multiple_files uses
    # args=[ARG_RFILES, ARG_WFILE], where the vararg consumes all but the
    # final writeable suffix argument.
    matched = resolve_observed_args_with_patterns(
        "cp",
        _args("foo", "bar", "baz"),
        [ArgMatcher.readable_files(), ArgMatcher.writeable_file()],
    )

    assert matched == [
        MatchedArg.new(0, ArgType.readable_file(), "foo"),
        MatchedArg.new(1, ArgType.readable_file(), "bar"),
        MatchedArg.new(2, ArgType.writeable_file(), "baz"),
    ]


def test_zero_or_more_vararg_allows_empty_like_ls_no_args() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_resolver.rs.
    # Rust suite anchor: tests/suite/ls.rs::test_ls_no_args allows
    # ARG_RFILES_OR_CWD to match zero observed positional args.
    assert (
        resolve_observed_args_with_patterns(
            "ls",
            [],
            [ArgMatcher.readable_files_or_cwd()],
        )
        == []
    )


def test_prefix_then_zero_or_more_vararg_like_rg_default_policy() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_resolver.rs.
    # Rust fixture anchor: src/default.policy defines rg args as
    # [ARG_OPAQUE_VALUE, ARG_RFILES_OR_CWD].
    matched = resolve_observed_args_with_patterns(
        "rg",
        _args("init", "src", "tests"),
        [ArgMatcher.opaque_non_file(), ArgMatcher.readable_files_or_cwd()],
    )

    assert matched == [
        MatchedArg.new(0, ArgType.opaque_non_file(), "init"),
        MatchedArg.new(1, ArgType.readable_file(), "src"),
        MatchedArg.new(2, ArgType.readable_file(), "tests"),
    ]


def test_literal_validation_error_propagates_from_matched_arg_new() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_resolver.rs.
    # Rust suite anchor: tests/suite/literal.rs invalid subcommand propagates
    # Error::LiteralValueDidNotMatch from ArgType validation.
    with pytest.raises(LiteralValueDidNotMatch) as exc_info:
        resolve_observed_args_with_patterns(
            "fake_executable",
            _args("subcommand", "not-a-real-subcommand"),
            [ArgMatcher.literal("subcommand"), ArgMatcher.literal("sub-subcommand")],
        )

    assert exc_info.value.to_mapping() == {
        "type": "LiteralValueDidNotMatch",
        "expected": "sub-subcommand",
        "actual": "not-a-real-subcommand",
    }


def test_not_enough_args_uses_suffix_count_like_cp_no_args() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_resolver.rs.
    # Rust suite anchor: tests/suite/cp.rs::test_cp_no_args returns
    # Error::NotEnoughArgs for [ARG_RFILES, ARG_WFILE] and zero args.
    patterns = [ArgMatcher.readable_files(), ArgMatcher.writeable_file()]

    with pytest.raises(NotEnoughArgs) as exc_info:
        resolve_observed_args_with_patterns("cp", [], patterns)

    assert exc_info.value.to_mapping() == {
        "type": "NotEnoughArgs",
        "program": "cp",
        "args": [],
        "arg_patterns": [
            {"type": "ReadableFiles"},
            {"type": "WriteableFile"},
        ],
    }


def test_at_least_one_vararg_must_match_like_cp_one_arg() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_resolver.rs.
    # Rust suite anchor: tests/suite/cp.rs::test_cp_one_arg returns
    # Error::VarargMatcherDidNotMatchAnything when only suffix input remains.
    with pytest.raises(VarargMatcherDidNotMatchAnything) as exc_info:
        resolve_observed_args_with_patterns(
            "cp",
            _args("foo/bar"),
            [ArgMatcher.readable_files(), ArgMatcher.writeable_file()],
        )

    assert exc_info.value.to_mapping() == {
        "type": "VarargMatcherDidNotMatchAnything",
        "program": "cp",
        "matcher": {"type": "ReadableFiles"},
    }


def test_extra_observed_args_are_reported_as_unexpected_arguments() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_resolver.rs.
    # Rust suite anchor: tests/suite/pwd.rs::test_pwd_extra_args reports all
    # observed positional args when no arg patterns match them.
    with pytest.raises(UnexpectedArguments) as exc_info:
        resolve_observed_args_with_patterns("pwd", _args("foo", "bar"), [])

    assert exc_info.value.to_mapping() == {
        "type": "UnexpectedArguments",
        "program": "pwd",
        "args": [
            {"index": 0, "value": "foo"},
            {"index": 1, "value": "bar"},
        ],
    }


def test_multiple_vararg_patterns_are_rejected_during_partitioning() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_resolver.rs.
    # Contract: partition_args permits at most one non-exact-cardinality
    # matcher, returning Error::MultipleVarargPatterns for a second one.
    with pytest.raises(MultipleVarargPatterns) as exc_info:
        resolve_observed_args_with_patterns(
            "tool",
            _args("a"),
            [ArgMatcher.readable_files(), ArgMatcher.unverified_varargs()],
        )

    assert exc_info.value.to_mapping() == {
        "type": "MultipleVarargPatterns",
        "program": "tool",
        "first": {"type": "ReadableFiles"},
        "second": {"type": "UnverifiedVarargs"},
    }


def test_exact_prefix_shortage_keeps_rust_range_error() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_resolver.rs.
    # Contract: exact-prefix shortage is caught by get_range_checked before
    # the later suffix NotEnoughArgs check.
    with pytest.raises(RangeEndOutOfBounds) as exc_info:
        resolve_observed_args_with_patterns(
            "fake_executable",
            _args("subcommand"),
            [ArgMatcher.literal("subcommand"), ArgMatcher.literal("sub-subcommand")],
        )

    assert exc_info.value.to_mapping() == {
        "type": "RangeEndOutOfBounds",
        "end": 2,
        "len": 1,
    }
