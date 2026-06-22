"""Rust-derived tests for codex-execpolicy/src/rule.rs example validation helpers."""

from __future__ import annotations

import pytest

from pycodex.execpolicy import (
    Decision,
    ExampleDidMatchError,
    ExampleDidNotMatchError,
    Policy,
    validate_match_examples,
    validate_not_match_examples,
)


def _policy_with_git_status_rule() -> tuple[Policy, tuple[object, ...]]:
    policy = Policy.empty()
    policy.add_prefix_rule(["git", "status"], Decision.ALLOW)
    return policy, policy.rules()["git"]


def test_validate_match_examples_accepts_examples_that_match_policy_rules():
    """Rust basic.rs: match_and_not_match_examples_are_enforced match examples."""
    policy, rules = _policy_with_git_status_rule()

    validate_match_examples(policy, rules, [["git", "status"], ["git", "status", "--short"]])


def test_validate_match_examples_rejects_unmatched_examples():
    """Rust rule.rs: validate_match_examples errors when any example has no rule match."""
    policy, rules = _policy_with_git_status_rule()

    with pytest.raises(ExampleDidNotMatchError) as excinfo:
        validate_match_examples(policy, rules, [["git", "status"], ["git", "branch", "--show-current"]])

    assert excinfo.value.examples == ("git branch --show-current",)
    assert "expected every example to match at least one rule" in str(excinfo.value)


def test_validate_not_match_examples_accepts_examples_that_do_not_match_policy_rules():
    """Rust basic.rs: match_and_not_match_examples_are_enforced not_match examples."""
    policy, rules = _policy_with_git_status_rule()

    validate_not_match_examples(
        policy,
        rules,
        [
            ["git", "--config", "color.status=always", "status"],
            ["git", "branch"],
        ],
    )


def test_validate_not_match_examples_rejects_matching_examples():
    """Rust rule.rs: validate_not_match_examples errors when a negative example matches."""
    policy, rules = _policy_with_git_status_rule()

    with pytest.raises(ExampleDidMatchError) as excinfo:
        validate_not_match_examples(policy, rules, [["git", "status"]])

    assert excinfo.value.example == "git status"
    assert str(excinfo.value).startswith("expected example to not match rule `")
