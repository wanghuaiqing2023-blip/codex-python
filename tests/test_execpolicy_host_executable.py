"""Rust-derived tests for parser.rs host_executable and policy.rs host resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.execpolicy import Decision, InvalidRuleError, MatchOptions, PolicyParser


def _allow_all(_: tuple[str, ...]) -> Decision:
    return Decision.ALLOW


def _prompt_all(_: tuple[str, ...]) -> Decision:
    return Decision.PROMPT


def test_policy_parser_parses_host_executable_paths(tmp_path):
    """Rust basic.rs: parses_host_executable_paths."""
    command_path = tmp_path / "host_cmd"
    parser = PolicyParser()

    parser.parse("test.rules", f'host_executable(name="host_cmd", paths=["{command_path.as_posix()}"])')
    policy = parser.build()

    assert policy.host_executables() == {"host_cmd": (str(command_path),)}


def test_host_executable_rejects_invalid_name_and_paths(tmp_path):
    """Rust basic.rs: host_executable validation failures."""
    parser = PolicyParser()
    with pytest.raises(InvalidRuleError, match="bare executable name"):
        parser.parse("test.rules", 'host_executable(name="bin/git", paths=[])')

    parser = PolicyParser()
    with pytest.raises(InvalidRuleError, match="paths must be absolute"):
        parser.parse("test.rules", 'host_executable(name="git", paths=["relative/git"])')

    wrong = tmp_path / "not_git"
    parser = PolicyParser()
    with pytest.raises(InvalidRuleError, match="must have basename `git`"):
        parser.parse("test.rules", f'host_executable(name="git", paths=["{wrong.as_posix()}"])')


def test_host_executable_last_definition_wins(tmp_path):
    """Rust basic.rs: host_executable_last_definition_wins."""
    first = tmp_path / "first" / "git"
    second = tmp_path / "second" / "git"
    parser = PolicyParser()

    parser.parse(
        "test.rules",
        "\n".join(
            [
                f'host_executable(name="git", paths=["{first.as_posix()}"])',
                f'host_executable(name="git", paths=["{second.as_posix()}"])',
            ]
        ),
    )

    assert parser.build().host_executables() == {"git": (str(second),)}


def test_host_executable_resolution_uses_basename_rule_when_allowed(tmp_path):
    """Rust basic.rs: host_executable_resolution_uses_basename_rule_when_allowed."""
    command_path = tmp_path / "git"
    parser = PolicyParser()
    parser.parse(
        "test.rules",
        "\n".join(
            [
                f'host_executable(name="git", paths=["{command_path.as_posix()}"])',
                'prefix_rule(pattern=["git", "status"], decision="allow")',
            ]
        ),
    )
    policy = parser.build()

    evaluation = policy.check_with_options(
        [str(command_path), "status"],
        _prompt_all,
        MatchOptions(resolve_host_executables=True),
    )

    assert evaluation.decision is Decision.ALLOW
    assert evaluation.matched_rules[0].matched_prefix == ("git", "status")
    assert evaluation.matched_rules[0].resolved_program == str(command_path)


def test_host_executable_resolution_respects_empty_and_mismatched_allowlists(tmp_path):
    """Rust basic.rs: empty/mismatched host executable allowlists do not resolve."""
    allowed_path = tmp_path / "allowed" / "git"
    other_path = tmp_path / "other" / "git"
    parser = PolicyParser()
    parser.parse(
        "test.rules",
        "\n".join(
            [
                f'host_executable(name="git", paths=["{allowed_path.as_posix()}"])',
                'prefix_rule(pattern=["git", "status"], decision="allow")',
            ]
        ),
    )
    policy = parser.build()

    evaluation = policy.check_with_options(
        [str(other_path), "status"],
        _prompt_all,
        MatchOptions(resolve_host_executables=True),
    )
    assert not evaluation.is_match()
    assert evaluation.decision is Decision.PROMPT

    empty_parser = PolicyParser()
    empty_parser.parse(
        "test.rules",
        'host_executable(name="git", paths=[])\nprefix_rule(pattern=["git", "status"], decision="allow")',
    )
    empty_policy = empty_parser.build()
    empty_eval = empty_policy.check_with_options(
        [str(allowed_path), "status"],
        _prompt_all,
        MatchOptions(resolve_host_executables=True),
    )
    assert not empty_eval.is_match()


def test_host_executable_resolution_falls_back_without_mapping(tmp_path):
    """Rust basic.rs: host_executable_resolution_falls_back_without_mapping."""
    command_path = tmp_path / "git"
    parser = PolicyParser()
    parser.parse("test.rules", 'prefix_rule(pattern=["git", "status"], decision="allow")')
    policy = parser.build()

    evaluation = policy.check_with_options(
        [str(command_path), "status"],
        _prompt_all,
        MatchOptions(resolve_host_executables=True),
    )

    assert evaluation.decision is Decision.ALLOW
    assert evaluation.matched_rules[0].resolved_program == str(command_path)


def test_host_executable_resolution_does_not_override_exact_match(tmp_path):
    """Rust basic.rs: host_executable_resolution_does_not_override_exact_match."""
    command_path = tmp_path / "git"
    parser = PolicyParser()
    parser.parse(
        "test.rules",
        "\n".join(
            [
                f'prefix_rule(pattern=["{command_path.as_posix()}", "status"], decision="forbidden")',
                'prefix_rule(pattern=["git", "status"], decision="allow")',
            ]
        ),
    )
    policy = parser.build()

    evaluation = policy.check_with_options(
        [command_path.as_posix(), "status"],
        _prompt_all,
        MatchOptions(resolve_host_executables=True),
    )

    assert evaluation.decision is Decision.FORBIDDEN
    assert evaluation.matched_rules[0].matched_prefix == (command_path.as_posix(), "status")
    assert evaluation.matched_rules[0].resolved_program is None

