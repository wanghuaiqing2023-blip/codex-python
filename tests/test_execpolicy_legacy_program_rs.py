"""Rust-derived tests for ``codex-execpolicy-legacy/src/program.rs``."""

from __future__ import annotations

import pytest

from pycodex.execpolicy_legacy import ArgMatcher
from pycodex.execpolicy_legacy import ArgType
from pycodex.execpolicy_legacy import DoubleDashNotSupportedYet
from pycodex.execpolicy_legacy import ExecCall
from pycodex.execpolicy_legacy import Forbidden
from pycodex.execpolicy_legacy import MatchedArg
from pycodex.execpolicy_legacy import MatchedExec
from pycodex.execpolicy_legacy import MatchedFlag
from pycodex.execpolicy_legacy import MatchedOpt
from pycodex.execpolicy_legacy import MissingRequiredOptions
from pycodex.execpolicy_legacy import NegativeExamplePassedCheck
from pycodex.execpolicy_legacy import Opt
from pycodex.execpolicy_legacy import OptionFollowedByOptionInsteadOfValue
from pycodex.execpolicy_legacy import OptionMissingValue
from pycodex.execpolicy_legacy import PositiveExampleFailedCheck
from pycodex.execpolicy_legacy import ProgramSpec
from pycodex.execpolicy_legacy import UnknownOption
from pycodex.execpolicy_legacy import ValidExec
from pycodex.execpolicy_legacy import VarargMatcherDidNotMatchAnything


def _ls_spec() -> ProgramSpec:
    return ProgramSpec.new(
        program="ls",
        system_path=["/bin/ls", "/usr/bin/ls"],
        option_bundling=False,
        combined_format=False,
        allowed_options={
            "-1": Opt.flag("-1"),
            "-a": Opt.flag("-a"),
            "-l": Opt.flag("-l"),
        },
        arg_patterns=[ArgMatcher.readable_files_or_cwd()],
    )


def _head_spec() -> ProgramSpec:
    return ProgramSpec.new(
        program="head",
        system_path=["/bin/head", "/usr/bin/head"],
        option_bundling=False,
        combined_format=False,
        allowed_options={
            "-c": Opt.value("-c", ArgMatcher.positive_integer()),
            "-n": Opt.value("-n", ArgMatcher.positive_integer()),
        },
        arg_patterns=[ArgMatcher.readable_files()],
    )


def test_program_spec_check_matches_ls_flags_and_positional_args() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/program.rs.
    # Rust suite anchor: tests/suite/ls.rs::test_ls_multiple_flags_and_file_args.
    result = _ls_spec().check(ExecCall.new("ls", ["-l", "-a", "foo", "bar", "baz"]))

    assert result == MatchedExec.match(
        ValidExec(
            program="ls",
            flags=(MatchedFlag.new("-l"), MatchedFlag.new("-a")),
            opts=(),
            args=(
                MatchedArg.new(2, ArgType.readable_file(), "foo"),
                MatchedArg.new(3, ArgType.readable_file(), "bar"),
                MatchedArg.new(4, ArgType.readable_file(), "baz"),
            ),
            system_path=("/bin/ls", "/usr/bin/ls"),
        )
    )


def test_program_spec_allows_flags_after_file_args_like_current_rust() -> None:
    # Rust suite anchor: tests/suite/ls.rs::test_flags_after_file_args. Rust
    # currently allows this even though the test comment notes ls itself may not.
    result = _ls_spec().check(ExecCall.new("ls", ["foo", "-l"]))

    assert result == MatchedExec.match(
        ValidExec(
            program="ls",
            flags=(MatchedFlag.new("-l"),),
            opts=(),
            args=(MatchedArg.new(0, ArgType.readable_file(), "foo"),),
            system_path=("/bin/ls", "/usr/bin/ls"),
        )
    )


def test_program_spec_rejects_unknown_and_bundled_options_like_ls() -> None:
    # Rust suite anchors: tests/suite/ls.rs::{test_ls_dash_z,test_ls_dash_al}.
    with pytest.raises(UnknownOption) as z_exc:
        _ls_spec().check(ExecCall.new("ls", ["-z"]))
    assert z_exc.value.to_mapping() == {
        "type": "UnknownOption",
        "program": "ls",
        "option": "-z",
    }

    with pytest.raises(UnknownOption) as bundled_exc:
        _ls_spec().check(ExecCall.new("ls", ["-al"]))
    assert bundled_exc.value.to_mapping() == {
        "type": "UnknownOption",
        "program": "ls",
        "option": "-al",
    }


def test_program_spec_option_value_and_negative_value_error_like_head() -> None:
    # Rust suite anchors: tests/suite/head.rs::{test_head_one_flag_one_file,
    # test_head_invalid_n_as_negative_int}. Option values that start with "-"
    # are rejected before ArgType validation.
    result = _head_spec().check(ExecCall.new("head", ["-n", "100", "src/extension.ts"]))

    assert result == MatchedExec.match(
        ValidExec(
            program="head",
            flags=(),
            opts=(MatchedOpt.new("-n", "100", ArgType.positive_integer()),),
            args=(MatchedArg.new(2, ArgType.readable_file(), "src/extension.ts"),),
            system_path=("/bin/head", "/usr/bin/head"),
        )
    )

    with pytest.raises(OptionFollowedByOptionInsteadOfValue) as exc_info:
        _head_spec().check(ExecCall.new("head", ["-n", "-1", "src/extension.ts"]))

    assert exc_info.value.to_mapping() == {
        "type": "OptionFollowedByOptionInsteadOfValue",
        "program": "head",
        "option": "-n",
        "value": "-1",
    }


def test_program_spec_reports_missing_option_value_and_double_dash() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/program.rs.
    # Contract: a trailing value-taking option produces OptionMissingValue, and
    # the standalone "--" sentinel is not supported.
    with pytest.raises(OptionMissingValue) as missing_exc:
        _head_spec().check(ExecCall.new("head", ["-n"]))
    assert missing_exc.value.to_mapping() == {
        "type": "OptionMissingValue",
        "program": "head",
        "option": "-n",
    }

    with pytest.raises(DoubleDashNotSupportedYet) as dash_exc:
        _ls_spec().check(ExecCall.new("ls", ["--"]))
    assert dash_exc.value.to_mapping() == {
        "type": "DoubleDashNotSupportedYet",
        "program": "ls",
    }


def test_program_spec_required_options_are_sorted_like_sed_e_spec() -> None:
    # Rust suite anchor: tests/suite/sed.rs::test_sed_reject_no_e_flag reports
    # MissingRequiredOptions for the required -e option. program.rs sorts
    # missing required option names before returning the error.
    spec = ProgramSpec.new(
        program="sed",
        system_path=["/usr/bin/sed"],
        option_bundling=False,
        combined_format=False,
        allowed_options={
            "-z": Opt.value("-z", ArgMatcher.opaque_non_file(), required=True),
            "-e": Opt.value("-e", ArgMatcher.sed_command(), required=True),
        },
        arg_patterns=[ArgMatcher.readable_files()],
    )

    with pytest.raises(MissingRequiredOptions) as exc_info:
        spec.check(ExecCall.new("sed", ["hello.txt"]))

    assert exc_info.value.to_mapping() == {
        "type": "MissingRequiredOptions",
        "program": "sed",
        "options": ["-e", "-z"],
    }


def test_program_spec_forbidden_program_returns_forbidden_exec_match() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/program.rs.
    # Contract: when ProgramSpec.forbidden is set, successful argument matching
    # returns MatchedExec::Forbidden with Forbidden::Exec cause.
    spec = ProgramSpec.new(
        program="tool",
        system_path=[],
        option_bundling=False,
        combined_format=False,
        allowed_options={},
        arg_patterns=[],
        forbidden="blocked by policy",
    )

    result = spec.check(ExecCall.new("tool", []))

    assert result == MatchedExec.forbidden(
        Forbidden.exec_cause(
            ValidExec(program="tool", flags=(), opts=(), args=(), system_path=())
        ),
        "blocked by policy",
    )


def test_program_spec_verify_example_lists_match_rust_shapes() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/program.rs.
    # Contract: verify_should_match_list records positive examples that fail;
    # verify_should_not_match_list records negative examples that pass.
    spec = ProgramSpec.new(
        program="cat",
        system_path=[],
        option_bundling=False,
        combined_format=False,
        allowed_options={},
        arg_patterns=[ArgMatcher.readable_files()],
        should_match=[[]],
        should_not_match=[["file.txt"]],
    )

    positive = spec.verify_should_match_list()
    negative = spec.verify_should_not_match_list()

    assert len(positive) == 1
    assert positive[0].program == "cat"
    assert positive[0].args == ()
    assert isinstance(positive[0].error, VarargMatcherDidNotMatchAnything)
    assert negative == [NegativeExamplePassedCheck(program="cat", args=("file.txt",))]
    assert PositiveExampleFailedCheck(
        program="cat",
        args=(),
        error=positive[0].error,
    ) == positive[0]
