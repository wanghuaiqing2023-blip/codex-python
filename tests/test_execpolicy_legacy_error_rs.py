"""Rust-derived tests for ``codex-execpolicy-legacy/src/error.rs``."""

from __future__ import annotations

from pathlib import Path

from pycodex.execpolicy_legacy.arg_matcher import ArgMatcher
from pycodex.execpolicy_legacy.error import CannotCanonicalizePath
from pycodex.execpolicy_legacy.error import CannotCheckRelativePath
from pycodex.execpolicy_legacy.error import DoubleDashNotSupportedYet
from pycodex.execpolicy_legacy.error import EmptyFileName
from pycodex.execpolicy_legacy.error import InternalInvariantViolation
from pycodex.execpolicy_legacy.error import InvalidPositiveInteger
from pycodex.execpolicy_legacy.error import LiteralValueDidNotMatch
from pycodex.execpolicy_legacy.error import MissingRequiredOptions
from pycodex.execpolicy_legacy.error import MultipleVarargPatterns
from pycodex.execpolicy_legacy.error import NoSpecForProgram
from pycodex.execpolicy_legacy.error import NotEnoughArgs
from pycodex.execpolicy_legacy.error import OptionFollowedByOptionInsteadOfValue
from pycodex.execpolicy_legacy.error import OptionMissingValue
from pycodex.execpolicy_legacy.arg_resolver import PositionalArg
from pycodex.execpolicy_legacy.error import PrefixOverlapsSuffix
from pycodex.execpolicy_legacy.error import RangeEndOutOfBounds
from pycodex.execpolicy_legacy.error import RangeStartExceedsEnd
from pycodex.execpolicy_legacy.error import ReadablePathNotInReadableFolders
from pycodex.execpolicy_legacy.error import SedCommandNotProvablySafe
from pycodex.execpolicy_legacy.error import UnexpectedArguments
from pycodex.execpolicy_legacy.error import UnknownOption
from pycodex.execpolicy_legacy.error import VarargMatcherDidNotMatchAnything
from pycodex.execpolicy_legacy.error import WriteablePathNotInWriteableFolders


def test_error_rs_variants_have_rust_tagged_mapping_shapes() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/error.rs.
    # Contract: Error is serde tagged by "type"; every Rust variant has a
    # Python projection with the same stable discriminant.
    matcher = ArgMatcher.readable_files()
    positional = PositionalArg(0, "value")
    errors = [
        NoSpecForProgram("prog"),
        OptionMissingValue("prog", "-n"),
        OptionFollowedByOptionInsteadOfValue("prog", "-n", "-x"),
        UnknownOption("prog", "-z"),
        UnexpectedArguments("prog", (positional,)),
        DoubleDashNotSupportedYet("prog"),
        MultipleVarargPatterns("prog", matcher, ArgMatcher.unverified_varargs()),
        RangeStartExceedsEnd(2, 1),
        RangeEndOutOfBounds(3, 2),
        PrefixOverlapsSuffix(),
        NotEnoughArgs("prog", (positional,), (matcher,)),
        InternalInvariantViolation("boom"),
        VarargMatcherDidNotMatchAnything("prog", matcher),
        EmptyFileName(),
        LiteralValueDidNotMatch("expected", "actual"),
        InvalidPositiveInteger("0"),
        MissingRequiredOptions("prog", ("--flag",)),
        SedCommandNotProvablySafe("s/foo/bar/"),
        ReadablePathNotInReadableFolders(Path("/tmp/file"), [Path("/tmp/root")]),
        WriteablePathNotInWriteableFolders(Path("/tmp/file"), [Path("/tmp/root")]),
        CannotCheckRelativePath(Path("relative")),
        CannotCanonicalizePath("bad", "NotFound"),
    ]

    assert [error.to_mapping()["type"] for error in errors] == [
        "NoSpecForProgram",
        "OptionMissingValue",
        "OptionFollowedByOptionInsteadOfValue",
        "UnknownOption",
        "UnexpectedArguments",
        "DoubleDashNotSupportedYet",
        "MultipleVarargPatterns",
        "RangeStartExceedsEnd",
        "RangeEndOutOfBounds",
        "PrefixOverlapsSuffix",
        "NotEnoughArgs",
        "InternalInvariantViolation",
        "VarargMatcherDidNotMatchAnything",
        "EmptyFileName",
        "LiteralValueDidNotMatch",
        "InvalidPositiveInteger",
        "MissingRequiredOptions",
        "SedCommandNotProvablySafe",
        "ReadablePathNotInReadableFolders",
        "WriteablePathNotInWriteableFolders",
        "CannotCheckRelativePath",
        "CannotCanonicalizePath",
    ]

    assert errors[-1].to_mapping() == {
        "type": "CannotCanonicalizePath",
        "file": "bad",
        "error": "NotFound",
    }
