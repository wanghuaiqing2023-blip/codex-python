"""Rust-derived tests for ``codex-execpolicy-legacy/src/policy_parser.rs``."""

from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.execpolicy_legacy import ArgType
from pycodex.execpolicy_legacy import ExecCall
from pycodex.execpolicy_legacy import Forbidden
from pycodex.execpolicy_legacy import MatchedArg
from pycodex.execpolicy_legacy import MatchedExec
from pycodex.execpolicy_legacy import MatchedFlag
from pycodex.execpolicy_legacy import MatchedOpt
from pycodex.execpolicy_legacy import MissingRequiredOptions
from pycodex.execpolicy_legacy import OptionFollowedByOptionInsteadOfValue
from pycodex.execpolicy_legacy import PolicyParser
from pycodex.execpolicy_legacy import ValidExec
from pycodex.execpolicy_legacy import get_default_policy


REPO_ROOT = Path(__file__).resolve().parents[1]
RUST_DEFAULT_POLICY = (
    REPO_ROOT / "codex" / "codex-rs" / "execpolicy-legacy" / "src" / "default.policy"
)


def test_policy_parser_builds_program_specs_and_builtin_arg_constants() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/policy_parser.rs.
    # Contract: PolicyParser::parse installs ARG_* constants and define_program
    # builds a Policy containing ProgramSpec entries keyed by program.
    policy = PolicyParser.new(
        "inline",
        """
define_program(
    program="fake",
    system_path=["/bin/fake"],
    options=[flag("-v"), opt("--count", ARG_POS_INT, required=True)],
    args=["subcommand", ARG_RFILES_OR_CWD],
    should_match=[["--count", "2", "subcommand"]],
    should_not_match=[["--count", "0", "subcommand"]],
)
""",
    ).parse()

    assert tuple(policy.programs) == ("fake",)
    spec = policy.programs["fake"][0]
    assert spec.system_path == ("/bin/fake",)
    assert spec.required_options == frozenset({"--count"})

    result = policy.check(ExecCall.new("fake", ["--count", "2", "subcommand", "src"]))
    assert result == MatchedExec.match(
        ValidExec(
            program="fake",
            flags=(),
            opts=(MatchedOpt.new("--count", "2", ArgType.positive_integer()),),
            args=(
                MatchedArg.new(2, ArgType.literal("subcommand"), "subcommand"),
                MatchedArg.new(3, ArgType.readable_file(), "src"),
            ),
            system_path=("/bin/fake",),
        )
    )


def test_policy_parser_rejects_duplicate_flags_like_rust_builtin() -> None:
    # Rust anchor: policy_builtins::define_program returns an error when two
    # options share the same Opt::name.
    with pytest.raises(ValueError, match="duplicate flag: -n"):
        PolicyParser.new(
            "duplicate",
            """
define_program(
    program="cat",
    options=[flag("-n"), opt("-n", ARG_POS_INT)],
)
""",
        ).parse()


def test_policy_parser_forbidden_builtins_feed_policy_checks() -> None:
    # Rust anchors: policy_builtins::{forbid_substrings,forbid_program_regex}
    # add policy-level forbidden checks before program spec dispatch.
    policy = PolicyParser.new(
        "forbidden",
        """
forbid_substrings(["secret."])
forbid_program_regex("^deploy$", "blocked deploy")
define_program(program="cat", args=[ARG_RFILES])
""",
    ).parse()

    assert policy.check(ExecCall.new("deploy", ["file.txt"])) == MatchedExec.forbidden(
        Forbidden.program_cause("deploy", ExecCall.new("deploy", ["file.txt"])),
        "blocked deploy",
    )
    assert policy.check(ExecCall.new("cat", ["secret.txt"])) == MatchedExec.forbidden(
        Forbidden.arg_cause("secret.txt", ExecCall.new("cat", ["secret.txt"])),
        "arg `secret.txt` contains forbidden substring",
    )


def test_policy_parser_extended_dialect_shape_used_by_default_policy() -> None:
    # Rust anchors: PolicyParser::parse uses Dialect::Extended with f-strings
    # enabled and executes Python-like policy expressions through Starlark.
    # Contract covered here: locals, list concatenation, f-string strings,
    # positional first argument, and Option<bool>::None defaulting to false.
    policy = PolicyParser.new(
        "extended",
        """
prefix = "safe"
base_flags = [flag("-n")]
more_flags = base_flags + [opt("--limit", ARG_POS_INT, required=None)]
define_program(
    f"{prefix}-cat",
    options=more_flags,
    args=[ARG_RFILES],
    system_path=[f"/bin/{prefix}-cat"],
)
""",
    ).parse()

    spec = policy.programs["safe-cat"][0]
    assert tuple(spec.allowed_options) == ("-n", "--limit")
    assert spec.required_options == frozenset()
    assert spec.system_path == ("/bin/safe-cat",)

    assert policy.check(
        ExecCall.new("safe-cat", ["-n", "--limit", "2", "file.txt"])
    ) == MatchedExec.match(
        ValidExec(
            program="safe-cat",
            flags=(MatchedFlag.new("-n"),),
            opts=(MatchedOpt.new("--limit", "2", ArgType.positive_integer()),),
            args=(MatchedArg.new(3, ArgType.readable_file(), "file.txt"),),
            system_path=("/bin/safe-cat",),
        )
    )


def test_get_default_policy_uses_upstream_rust_default_policy_fixture() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/lib.rs get_default_policy
    # parses include_str!("default.policy"). Python reads the same Rust file in
    # this porting workspace.
    assert RUST_DEFAULT_POLICY.exists()

    policy = get_default_policy()

    assert len(policy.programs["sed"]) == 2
    assert len(policy.programs["printenv"]) == 2
    assert policy.check_each_good_list_individually() == []
    assert policy.check_each_bad_list_individually() == []


def test_default_policy_matches_representative_rust_suite_behaviors() -> None:
    # Rust suite anchors: tests/suite/{head,sed,rg}.rs and default.policy.
    policy = get_default_policy()

    assert policy.check(ExecCall.new("head", ["-n", "100", "src/extension.ts"])) == (
        MatchedExec.match(
            ValidExec(
                program="head",
                flags=(),
                opts=(MatchedOpt.new("-n", "100", ArgType.positive_integer()),),
                args=(MatchedArg.new(2, ArgType.readable_file(), "src/extension.ts"),),
                system_path=("/bin/head", "/usr/bin/head"),
            )
        )
    )

    assert policy.check(ExecCall.new("sed", ["-n", "122,202p", "hello.txt"])) == (
        MatchedExec.match(
            ValidExec(
                program="sed",
                flags=(MatchedFlag.new("-n"),),
                opts=(),
                args=(
                    MatchedArg.new(1, ArgType.sed_command(), "122,202p"),
                    MatchedArg.new(2, ArgType.readable_file(), "hello.txt"),
                ),
                system_path=("/usr/bin/sed",),
            )
        )
    )

    with pytest.raises(MissingRequiredOptions) as missing_e:
        policy.check(ExecCall.new("sed", ["122,202p"]))
    assert missing_e.value.to_mapping() == {
        "type": "MissingRequiredOptions",
        "program": "sed",
        "options": ["-e"],
    }

    try:
        policy.check(ExecCall.new("rg", ["-m", "-n", "init"]))
    except OptionFollowedByOptionInsteadOfValue as exc:
        assert exc.to_mapping() == {
            "type": "OptionFollowedByOptionInsteadOfValue",
            "program": "rg",
            "option": "-m",
            "value": "-n",
        }
    else:
        raise AssertionError("expected OptionFollowedByOptionInsteadOfValue")
