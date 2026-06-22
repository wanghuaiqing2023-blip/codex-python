"""Rust-derived tests for ``codex-execpolicy-legacy/src/policy.rs``."""

from __future__ import annotations

import pytest

from pycodex.execpolicy_legacy import ArgMatcher
from pycodex.execpolicy_legacy import ArgType
from pycodex.execpolicy_legacy import ExecCall
from pycodex.execpolicy_legacy import Forbidden
from pycodex.execpolicy_legacy import ForbiddenProgramRegex
from pycodex.execpolicy_legacy import MatchedArg
from pycodex.execpolicy_legacy import MatchedExec
from pycodex.execpolicy_legacy import NegativeExamplePassedCheck
from pycodex.execpolicy_legacy import NoSpecForProgram
from pycodex.execpolicy_legacy import Opt
from pycodex.execpolicy_legacy import Policy
from pycodex.execpolicy_legacy import ProgramSpec
from pycodex.execpolicy_legacy import UnknownOption
from pycodex.execpolicy_legacy import ValidExec
from pycodex.execpolicy_legacy import VarargMatcherDidNotMatchAnything


def _cat_spec() -> ProgramSpec:
    return ProgramSpec.new(
        program="cat",
        system_path=["/bin/cat", "/usr/bin/cat"],
        option_bundling=False,
        combined_format=False,
        allowed_options={"-n": Opt.flag("-n")},
        arg_patterns=[ArgMatcher.readable_files()],
    )


def test_policy_check_returns_forbidden_program_before_specs() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/policy.rs.
    # Contract: Policy::check evaluates forbidden_program_regexes before
    # looking up any program specs.
    policy = Policy.new(
        programs={"deploy": (_cat_spec(),)},
        forbidden_program_regexes=[
            ForbiddenProgramRegex(regex=r"^deploy$", reason="blocked deploy"),
        ],
    )
    exec_call = ExecCall.new("deploy", ["file.txt"])

    assert policy.check(exec_call) == MatchedExec.forbidden(
        Forbidden.program_cause("deploy", exec_call),
        "blocked deploy",
    )


def test_policy_check_returns_forbidden_arg_before_specs() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/policy.rs.
    # Contract: forbidden substrings are escaped and joined into one regex; the
    # first matching arg returns Forbidden::Arg with Rust's reason text.
    policy = Policy.new(
        programs={"cat": (_cat_spec(),)},
        forbidden_substrings=["$(rm -rf /)", "secret."],
    )
    exec_call = ExecCall.new("cat", ["notes/secret.txt"])

    assert policy.check(exec_call) == MatchedExec.forbidden(
        Forbidden.arg_cause("notes/secret.txt", exec_call),
        "arg `notes/secret.txt` contains forbidden substring",
    )


def test_policy_check_selects_first_successful_program_spec() -> None:
    # Rust suite connection: default policy has multiple specs for printenv and
    # sed. Policy::check tries specs for the program in insertion order and
    # returns the first successful match.
    zero_arg = ProgramSpec.new(
        program="printenv",
        system_path=["/usr/bin/printenv"],
        option_bundling=False,
        combined_format=False,
        allowed_options={},
        arg_patterns=[],
    )
    one_arg = ProgramSpec.new(
        program="printenv",
        system_path=["/usr/bin/printenv"],
        option_bundling=False,
        combined_format=False,
        allowed_options={},
        arg_patterns=[ArgMatcher.opaque_non_file()],
    )
    policy = Policy.new(programs={"printenv": (zero_arg, one_arg)})

    assert policy.check(ExecCall.new("printenv", ["PATH"])) == MatchedExec.match(
        ValidExec(
            program="printenv",
            flags=(),
            opts=(),
            args=(MatchedArg.new(0, ArgType.opaque_non_file(), "PATH"),),
            system_path=("/usr/bin/printenv",),
        )
    )


def test_policy_check_returns_last_error_when_all_specs_fail() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/policy.rs.
    # Contract: if program specs exist but all fail, Policy::check returns the
    # last spec error, not NoSpecForProgram.
    literal_arg = ProgramSpec.new(
        program="tool",
        system_path=[],
        option_bundling=False,
        combined_format=False,
        allowed_options={},
        arg_patterns=[ArgMatcher.literal("subcommand")],
    )
    one_arg = ProgramSpec.new(
        program="tool",
        system_path=[],
        option_bundling=False,
        combined_format=False,
        allowed_options={},
        arg_patterns=[ArgMatcher.readable_files()],
    )
    policy = Policy.new(programs={"tool": (literal_arg, one_arg)})

    with pytest.raises(VarargMatcherDidNotMatchAnything):
        policy.check(ExecCall.new("tool", []))


def test_policy_check_no_spec_for_program() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/policy.rs.
    # Contract: when no specs exist for the program, check returns
    # Error::NoSpecForProgram.
    policy = Policy.new(programs={})

    with pytest.raises(NoSpecForProgram) as exc_info:
        policy.check(ExecCall.new("missing", []))

    assert exc_info.value.to_mapping() == {
        "type": "NoSpecForProgram",
        "program": "missing",
    }


def test_policy_good_and_bad_list_aggregation() -> None:
    # Rust suite anchors: tests/suite/good.rs and tests/suite/bad.rs call
    # Policy::{check_each_good_list_individually,check_each_bad_list_individually}.
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
    policy = Policy.new(programs={"cat": (spec,)})

    good_violations = policy.check_each_good_list_individually()
    bad_violations = policy.check_each_bad_list_individually()

    assert len(good_violations) == 1
    assert isinstance(good_violations[0].error, VarargMatcherDidNotMatchAnything)
    assert bad_violations == [
        NegativeExamplePassedCheck(program="cat", args=("file.txt",))
    ]


def test_policy_forbidden_checks_precede_program_errors() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/policy.rs.
    # Contract: forbidden args are checked before program spec errors, so an
    # otherwise unknown option is returned as forbidden when it contains a
    # forbidden substring.
    policy = Policy.new(
        programs={"cat": (_cat_spec(),)},
        forbidden_substrings=["-z"],
    )
    result = policy.check(ExecCall.new("cat", ["-z"]))

    assert result.kind == "Forbidden"
    assert result.cause == Forbidden.arg_cause("-z", ExecCall.new("cat", ["-z"]))

    plain_policy = Policy.new(programs={"cat": (_cat_spec(),)})
    with pytest.raises(UnknownOption):
        plain_policy.check(ExecCall.new("cat", ["-z"]))
