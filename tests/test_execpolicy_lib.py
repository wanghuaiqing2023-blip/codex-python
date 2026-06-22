"""Rust-derived tests for codex-execpolicy/src/lib.rs public export surface."""

from __future__ import annotations

from pathlib import Path

import pytest

import pycodex.execpolicy as execpolicy
from pycodex.execpolicy import (
    AmendError,
    Decision,
    Error,
    ErrorLocation,
    Evaluation,
    ExecPolicyCheckCommand,
    ExecPolicyError,
    MatchOptions,
    NetworkRuleProtocol,
    PatternToken,
    Policy,
    PolicyParser,
    PrefixPattern,
    PrefixRule,
    Rule,
    RuleMatch,
    RuleRef,
    TextPosition,
    TextRange,
    blocking_append_allow_prefix_rule,
    blocking_append_network_rule,
)


def test_lib_public_exports_are_available_from_package_root():
    """Rust lib.rs: pub use surface is available from pycodex.execpolicy."""
    expected = {
        "AmendError": AmendError,
        "blocking_append_allow_prefix_rule": blocking_append_allow_prefix_rule,
        "blocking_append_network_rule": blocking_append_network_rule,
        "Decision": Decision,
        "Error": Error,
        "ErrorLocation": ErrorLocation,
        "TextPosition": TextPosition,
        "TextRange": TextRange,
        "ExecPolicyCheckCommand": ExecPolicyCheckCommand,
        "PolicyParser": PolicyParser,
        "Evaluation": Evaluation,
        "MatchOptions": MatchOptions,
        "Policy": Policy,
        "NetworkRuleProtocol": NetworkRuleProtocol,
        "PatternToken": PatternToken,
        "PrefixPattern": PrefixPattern,
        "PrefixRule": PrefixRule,
        "Rule": Rule,
        "RuleMatch": RuleMatch,
        "RuleRef": RuleRef,
    }

    for name, value in expected.items():
        assert getattr(execpolicy, name) is value
        assert name in execpolicy.__all__


def test_error_alias_points_to_execpolicy_error_base():
    """Rust lib.rs re-exports Error; Python aliases it to the execpolicy error base."""
    assert Error is ExecPolicyError


def test_match_options_defaults_match_rust_default():
    """Rust policy.rs: MatchOptions default resolve_host_executables is false."""
    assert MatchOptions().resolve_host_executables is False
    assert MatchOptions(resolve_host_executables=True).resolve_host_executables is True


def test_policy_parser_parses_restricted_prefix_slice_and_blocks_host_executable():
    """Rust lib.rs exposes PolicyParser; Python supports the restricted prefix/network parser slice."""
    parser = PolicyParser()
    built = parser.build()
    assert built.rules() == {}
    assert built.network_rules() == ()

    parser.parse("test.rules", 'prefix_rule(pattern=["git"])')
    assert "git" in parser.build().rules()

    command_path = Path.cwd() / "git"
    parser.parse("test.rules", f'host_executable(name="git", paths=["{command_path.as_posix()}"])')
    assert parser.build().host_executables() == {"git": (str(command_path),)}


def test_exec_policy_check_command_normalizes_fields_and_blocks_on_load_policies(tmp_path):
    """Rust execpolicycheck.rs command shape is exposed; run blocks until load_policies is complete."""
    rules = tmp_path / "rules.star"
    command = ExecPolicyCheckCommand(
        rules=[rules],
        command=["git", "status"],
        pretty=True,
        resolve_host_executables=True,
    )

    assert command.rules == (Path(rules),)
    assert command.command == ("git", "status")
    assert command.pretty is True
    assert command.resolve_host_executables is True

    with pytest.raises(OSError, match="failed to read policy at"):
        command.run()


