"""Rust-derived tests for a codex-execpolicy/src/policy.rs direct API slice."""

from __future__ import annotations

import pytest

from pycodex.execpolicy import (
    Decision,
    Evaluation,
    InvalidPatternError,
    InvalidRuleError,
    NetworkRuleProtocol,
    PatternToken,
    Policy,
    PrefixPattern,
    PrefixRule,
    RuleMatch,
)


def _allow_all(_: tuple[str, ...]) -> Decision:
    return Decision.ALLOW


def _prompt_all(_: tuple[str, ...]) -> Decision:
    return Decision.PROMPT


def test_network_rules_compile_into_domain_lists_direct_policy_api():
    """Rust basic.rs: network_rules_compile_into_domain_lists, via Policy::add_network_rule."""
    policy = Policy.empty()
    policy.add_network_rule("google.com", NetworkRuleProtocol.HTTP, Decision.ALLOW)
    policy.add_network_rule("api.github.com", "https", Decision.ALLOW)
    policy.add_network_rule("blocked.example.com", NetworkRuleProtocol.HTTPS, Decision.FORBIDDEN)
    policy.add_network_rule("prompt-only.example.com", NetworkRuleProtocol.HTTPS, Decision.PROMPT)

    assert len(policy.network_rules()) == 4
    assert policy.network_rules()[1].protocol is NetworkRuleProtocol.HTTPS
    assert policy.compiled_network_domains() == (
        ["google.com", "api.github.com"],
        ["blocked.example.com"],
    )


def test_compiled_network_domains_last_allow_or_deny_for_host_wins():
    """Rust policy.rs: compiled_network_domains removes an overridden host from the opposite list."""
    policy = Policy.empty()
    policy.add_network_rule("api.github.com", NetworkRuleProtocol.HTTPS, Decision.ALLOW)
    policy.add_network_rule("api.github.com", NetworkRuleProtocol.HTTPS, Decision.FORBIDDEN)
    policy.add_network_rule("blocked.example.com", NetworkRuleProtocol.HTTPS, Decision.FORBIDDEN)
    policy.add_network_rule("blocked.example.com", NetworkRuleProtocol.HTTPS, Decision.ALLOW)

    assert policy.compiled_network_domains() == (["blocked.example.com"], ["api.github.com"])


def test_add_prefix_rule_extends_policy_and_matches_command():
    """Rust basic.rs: add_prefix_rule_extends_policy."""
    policy = Policy.empty()
    policy.add_prefix_rule(["ls", "-l"], Decision.PROMPT)

    assert policy.rules()["ls"] == (
        PrefixRule(
            pattern=PrefixPattern(first="ls", rest=(PatternToken.single("-l"),)),
            decision=Decision.PROMPT,
            justification=None,
        ),
    )

    evaluation = policy.check(["ls", "-l", "/some/important/folder"], _allow_all)
    assert evaluation == Evaluation(
        decision=Decision.PROMPT,
        matched_rules=(
            RuleMatch.prefix_rule_match(["ls", "-l"], Decision.PROMPT),
        ),
    )
    assert evaluation.is_match()


def test_add_prefix_rule_rejects_empty_prefix():
    """Rust basic.rs: add_prefix_rule_rejects_empty_prefix."""
    policy = Policy.empty()

    with pytest.raises(InvalidPatternError) as excinfo:
        policy.add_prefix_rule([], Decision.ALLOW)

    assert str(excinfo.value) == "invalid pattern element: prefix cannot be empty"


def test_heuristics_match_is_returned_when_no_policy_matches():
    """Rust basic.rs: heuristics_match_is_returned_when_no_policy_matches."""
    policy = Policy.empty()

    evaluation = policy.check(["unknown", "command"], _prompt_all)

    assert evaluation == Evaluation(
        decision=Decision.PROMPT,
        matched_rules=(
            RuleMatch.heuristics_rule_match(["unknown", "command"], Decision.PROMPT),
        ),
    )
    assert not evaluation.is_match()


def test_add_network_rule_rejects_empty_justification_and_wildcard_host():
    """Rust basic.rs: justification_cannot_be_empty and network_rule_rejects_wildcard_hosts."""
    policy = Policy.empty()

    with pytest.raises(InvalidRuleError, match="justification cannot be empty"):
        policy.add_network_rule("api.github.com", NetworkRuleProtocol.HTTPS, Decision.PROMPT, "   ")

    with pytest.raises(InvalidRuleError, match="wildcards are not allowed"):
        policy.add_network_rule("*", NetworkRuleProtocol.HTTP, Decision.ALLOW)
