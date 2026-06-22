"""Rust-derived tests for codex-execpolicy/src/execpolicycheck.rs."""

from __future__ import annotations

import json

import pytest

from pycodex.execpolicy import Decision, RuleMatch, format_matches_json, load_policies


def test_format_matches_json_compact_prefix_match():
    """Rust: format_matches_json serializes matchedRules and strongest decision compactly."""
    rendered = format_matches_json(
        [RuleMatch.prefix_rule_match(["echo", "hello"], Decision.ALLOW)],
        pretty=False,
    )

    assert rendered == (
        '{"matchedRules":[{"prefixRuleMatch":{"matchedPrefix":["echo","hello"],'
        '"decision":"allow"}}],"decision":"allow"}'
    )


def test_format_matches_json_omits_decision_for_empty_matches():
    """Rust: ExecPolicyCheckOutput skips decision when matched_rules is empty."""
    assert format_matches_json([], pretty=False) == '{"matchedRules":[]}'


def test_format_matches_json_pretty_and_optional_prefix_fields():
    """Rust: pretty output and prefix-rule optional fields use camelCase serde shape."""
    rendered = format_matches_json(
        [
            RuleMatch.prefix_rule_match(
                ["git", "push"],
                Decision.FORBIDDEN,
                resolved_program="/usr/bin/git",
                justification="pushing is blocked in this repo",
            )
        ],
        pretty=True,
    )

    payload = json.loads(rendered)
    assert "\n  " in rendered
    assert payload == {
        "matchedRules": [
            {
                "prefixRuleMatch": {
                    "matchedPrefix": ["git", "push"],
                    "decision": "forbidden",
                    "resolvedProgram": "/usr/bin/git",
                    "justification": "pushing is blocked in this repo",
                }
            }
        ],
        "decision": "forbidden",
    }


def test_format_matches_json_uses_strictest_decision_across_matches():
    """Rust: format_matches_json decision is max RuleMatch::decision."""
    payload = json.loads(
        format_matches_json(
            [
                RuleMatch.prefix_rule_match(["git"], Decision.PROMPT),
                RuleMatch.prefix_rule_match(["git", "commit"], Decision.FORBIDDEN),
            ]
        )
    )

    assert payload["decision"] == "forbidden"


def test_load_policies_returns_empty_policy_for_empty_path_list():
    """Rust: load_policies builds an empty parser when no files are provided."""
    policy = load_policies([])
    assert policy.rules() == {}
    assert policy.network_rules() == ()
