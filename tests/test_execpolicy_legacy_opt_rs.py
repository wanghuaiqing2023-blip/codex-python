"""Rust-derived tests for ``codex-execpolicy-legacy/src/opt.rs``."""

from __future__ import annotations

from pycodex.execpolicy_legacy import ArgMatcher
from pycodex.execpolicy_legacy import ArgType
from pycodex.execpolicy_legacy import Opt
from pycodex.execpolicy_legacy import OptMeta


def test_opt_new_stores_name_meta_and_required_flag() -> None:
    # Rust crate/module: codex-execpolicy-legacy/src/opt.rs.
    # Contract: Opt::new stores opt, meta, and required unchanged; Opt::name
    # returns the command-line option string.
    opt = Opt.new("--max-depth", OptMeta.value(ArgType.positive_integer()), True)

    assert opt.opt == "--max-depth"
    assert opt.name() == "--max-depth"
    assert opt.meta == OptMeta.value(ArgType.positive_integer())
    assert opt.required is True


def test_flag_builtin_projection_matches_policy_parser_flag() -> None:
    # Rust anchor: src/policy_parser.rs policy_builtins::flag constructs
    # Opt::new(name, OptMeta::Flag, false). Default policy uses this for
    # ls/pwd/sed flags.
    flag = Opt.flag("-a")

    assert flag == Opt.new("-a", OptMeta.flag(), False)
    assert str(flag) == "opt(-a)"
    assert flag.to_mapping() == {
        "opt": "-a",
        "meta": {"type": "Flag"},
        "required": False,
    }


def test_value_opt_projection_matches_policy_parser_opt_default_required() -> None:
    # Rust anchor: src/policy_parser.rs policy_builtins::opt constructs
    # OptMeta::Value(type.arg_type()) and required.unwrap_or(false). Default
    # policy uses opt("-n", ARG_POS_INT) for head.
    opt = Opt.value("-n", ArgMatcher.positive_integer())

    assert opt == Opt.new("-n", OptMeta.value(ArgType.positive_integer()), False)
    assert opt.to_mapping() == {
        "opt": "-n",
        "meta": {
            "type": "Value",
            "arg_type": {"type": "PositiveInteger"},
        },
        "required": False,
    }


def test_value_opt_projection_preserves_required_true() -> None:
    # Rust fixture anchor: src/default.policy sed second spec uses
    # opt("-e", ARG_SED_COMMAND, required=True).
    opt = Opt.value("-e", ArgMatcher.sed_command(), required=True)

    assert opt.required is True
    assert opt.meta == OptMeta.value(ArgType.sed_command())


def test_value_opt_projects_matcher_to_arg_type() -> None:
    # Rust anchor: policy_builtins::opt stores r#type.arg_type(), so vararg
    # matchers collapse to their argument value type inside OptMeta::Value.
    assert Opt.value("--glob", ArgMatcher.opaque_non_file()).meta == OptMeta.value(
        ArgType.opaque_non_file()
    )
    assert Opt.value("--mystery", ArgMatcher.unverified_varargs()).meta == OptMeta.value(
        ArgType.unknown()
    )
