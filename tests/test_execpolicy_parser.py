"""Rust-derived tests for a restricted codex-execpolicy/src/parser.rs slice."""

from __future__ import annotations

import json

import pytest

from pycodex.execpolicy import (
    Decision,
    InvalidRuleError,
    NetworkRuleProtocol,
    PolicyParser,
    format_matches_json,
    load_policies,
)


def test_policy_parser_parses_prefix_rule_and_default_allow_decision():
    """Rust basic.rs: basic_match with default Decision::Allow."""
    parser = PolicyParser()
    parser.parse("test.rules", 'prefix_rule(pattern=["git", "status"])')
    policy = parser.build()

    evaluation = policy.check(["git", "status"], lambda _: Decision.PROMPT)

    assert evaluation.decision is Decision.ALLOW
    assert evaluation.matched_rules[0].matched_prefix == ("git", "status")


def test_policy_parser_parses_justification_and_alternative_first_token():
    """Rust basic.rs: only_first_token_alias_expands_to_multiple_rules."""
    parser = PolicyParser()
    parser.parse(
        "test.rules",
        'prefix_rule(pattern=[["npm", "pnpm"], "publish"], decision="forbidden", '
        'justification="publishing is blocked")',
    )
    policy = parser.build()

    npm_eval = policy.check(["npm", "publish"], lambda _: Decision.ALLOW)
    pnpm_eval = policy.check(["pnpm", "publish"], lambda _: Decision.ALLOW)

    assert npm_eval.decision is Decision.FORBIDDEN
    assert pnpm_eval.decision is Decision.FORBIDDEN
    assert npm_eval.matched_rules[0].justification == "publishing is blocked"


def test_policy_parser_enforces_match_and_not_match_examples():
    """Rust basic.rs: match_and_not_match_examples_are_enforced parser validation."""
    parser = PolicyParser()
    parser.parse(
        "test.rules",
        'prefix_rule(pattern=["git", "status"], match=[["git", "status"], "git status"], '
        'not_match=[["git", "--config", "color.status=always", "status"]])',
    )
    policy = parser.build()

    assert policy.check(["git", "status"], lambda _: Decision.ALLOW).is_match()
    assert not policy.check(
        ["git", "--config", "color.status=always", "status"],
        lambda _: Decision.ALLOW,
    ).is_match()


def test_policy_parser_rejects_invalid_match_example():
    """Rust parser.rs: validate_pending_examples_from rejects unmatched match examples."""
    parser = PolicyParser()

    with pytest.raises(Exception, match="expected every example to match"):
        parser.parse(
            "test.rules",
            'prefix_rule(pattern=["echo", "hello"], decision="allow", match=[["echo", "bad"]])',
        )


def test_policy_parser_parses_network_rule_deny_alias_and_prompt_ignored_by_domain_lists():
    """Rust basic.rs: network_rules_compile_into_domain_lists and deny alias."""
    parser = PolicyParser()
    parser.parse(
        "network.rules",
        '\n'.join(
            [
                'network_rule(host="google.com", protocol="http", decision="allow")',
                'network_rule(host="api.github.com", protocol="https", decision="allow")',
                'network_rule(host="blocked.example.com", protocol="https", decision="deny")',
                'network_rule(host="prompt-only.example.com", protocol="https", decision="prompt")',
            ]
        ),
    )
    policy = parser.build()

    assert len(policy.network_rules()) == 4
    assert policy.network_rules()[1].protocol is NetworkRuleProtocol.HTTPS
    assert policy.compiled_network_domains() == (
        ["google.com", "api.github.com"],
        ["blocked.example.com"],
    )


def test_load_policies_and_execpolicycheck_success_path(tmp_path):
    """Rust execpolicycheck.rs: load_policies feeds parser.build into format_matches_json."""
    policy_path = tmp_path / "policy.rules"
    policy_path.write_text('prefix_rule(pattern=["echo", "hello"], decision="allow")\n', encoding="utf-8")

    policy = load_policies([policy_path])
    rendered = format_matches_json(policy.matches_for_command(["echo", "hello"], None))

    assert json.loads(rendered) == {
        "matchedRules": [
            {"prefixRuleMatch": {"matchedPrefix": ["echo", "hello"], "decision": "allow"}}
        ],
        "decision": "allow",
    }


def test_policy_parser_parses_host_executable_after_host_slice(tmp_path):
    """Rust parser.rs host_executable registration is covered by the host-executable slice."""
    command_path = tmp_path / "git"
    parser = PolicyParser()
    parser.parse("test.rules", f'host_executable(name="git", paths=["{command_path.as_posix()}"])')

    assert parser.build().host_executables() == {"git": (str(command_path),)}
