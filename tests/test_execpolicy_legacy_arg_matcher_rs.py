"""Rust-derived tests for ``codex-execpolicy-legacy/src/arg_matcher.rs``."""

from __future__ import annotations

import pytest

from pycodex.execpolicy_legacy import ArgMatcher
from pycodex.execpolicy_legacy import ArgMatcherCardinality
from pycodex.execpolicy_legacy import ArgType


@pytest.mark.parametrize(
    "matcher",
    [
        ArgMatcher.literal("subcommand"),
        ArgMatcher.opaque_non_file(),
        ArgMatcher.readable_file(),
        ArgMatcher.writeable_file(),
        ArgMatcher.positive_integer(),
        ArgMatcher.sed_command(),
    ],
)
def test_single_argument_matchers_have_exact_one_cardinality(matcher: ArgMatcher) -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_matcher.rs.
    # Contract: Literal, OpaqueNonFile, ReadableFile, WriteableFile,
    # PositiveInteger, and SedCommand map to ArgMatcherCardinality::One.
    cardinality = matcher.cardinality()

    assert cardinality is ArgMatcherCardinality.ONE
    assert cardinality.is_exact() == 1


def test_vararg_matchers_have_non_exact_cardinality() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_matcher.rs.
    # Rust suite anchors: cp/head use ReadableFiles; default.policy uses
    # ReadableFilesOrCwd and UnverifiedVarargs.
    assert ArgMatcher.readable_files().cardinality() is ArgMatcherCardinality.AT_LEAST_ONE
    assert ArgMatcher.readable_files().cardinality().is_exact() is None
    assert ArgMatcher.readable_files_or_cwd().cardinality() is ArgMatcherCardinality.ZERO_OR_MORE
    assert ArgMatcher.unverified_varargs().cardinality() is ArgMatcherCardinality.ZERO_OR_MORE
    assert ArgMatcher.unverified_varargs().cardinality().is_exact() is None


@pytest.mark.parametrize(
    ("matcher", "expected_arg_type"),
    [
        (ArgMatcher.literal("subcommand"), ArgType.literal("subcommand")),
        (ArgMatcher.opaque_non_file(), ArgType.opaque_non_file()),
        (ArgMatcher.readable_file(), ArgType.readable_file()),
        (ArgMatcher.writeable_file(), ArgType.writeable_file()),
        (ArgMatcher.readable_files(), ArgType.readable_file()),
        (ArgMatcher.readable_files_or_cwd(), ArgType.readable_file()),
        (ArgMatcher.positive_integer(), ArgType.positive_integer()),
        (ArgMatcher.sed_command(), ArgType.sed_command()),
        (ArgMatcher.unverified_varargs(), ArgType.unknown()),
    ],
)
def test_arg_matcher_projects_to_rust_arg_type(
    matcher: ArgMatcher,
    expected_arg_type: ArgType,
) -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_matcher.rs.
    # Contract: ArgMatcher::arg_type maps matcher variants to ArgType.
    assert matcher.arg_type() == expected_arg_type


def test_unpack_value_treats_strings_as_literal_matchers() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_matcher.rs
    # UnpackValue implementation.
    assert ArgMatcher.unpack_value("status") == ArgMatcher.literal("status")
    matcher = ArgMatcher.sed_command()
    assert ArgMatcher.unpack_value(matcher) == matcher
    assert ArgMatcher.unpack_value(123) is None


def test_arg_matcher_mapping_shape_matches_rust_variant_names() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/arg_matcher.rs.
    # Contract: Python keeps Rust variant names for status/debug projections.
    assert ArgMatcher.literal("x").to_mapping() == {"type": "Literal", "value": "x"}
    assert ArgMatcher.readable_files_or_cwd().to_mapping() == {"type": "ReadableFilesOrCwd"}
    assert ArgMatcher.unverified_varargs().to_mapping() == {"type": "UnverifiedVarargs"}
