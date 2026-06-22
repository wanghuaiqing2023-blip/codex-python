"""Rust-derived tests for codex-execpolicy/src/amend.rs."""

from __future__ import annotations

import pytest

from pycodex.execpolicy import (
    AmendError,
    Decision,
    NetworkRuleProtocol,
    blocking_append_allow_prefix_rule,
    blocking_append_network_rule,
    normalize_network_rule_host,
)


def test_appends_rule_and_creates_directories(tmp_path):
    """Rust: codex-execpolicy/src/amend.rs appends_rule_and_creates_directories."""
    policy_path = tmp_path / "rules" / "default.rules"

    blocking_append_allow_prefix_rule(policy_path, ["echo", "Hello, world!"])

    assert policy_path.read_text(encoding="utf-8") == (
        'prefix_rule(pattern=["echo", "Hello, world!"], decision="allow")\n'
    )


def test_appends_rule_without_duplicate_newline(tmp_path):
    """Rust: codex-execpolicy/src/amend.rs appends_rule_without_duplicate_newline."""
    policy_path = tmp_path / "rules" / "default.rules"
    policy_path.parent.mkdir()
    policy_path.write_text('prefix_rule(pattern=["ls"], decision="allow")\n', encoding="utf-8")

    blocking_append_allow_prefix_rule(policy_path, ["echo", "Hello, world!"])
    blocking_append_allow_prefix_rule(policy_path, ["echo", "Hello, world!"])

    assert policy_path.read_text(encoding="utf-8") == (
        'prefix_rule(pattern=["ls"], decision="allow")\n'
        'prefix_rule(pattern=["echo", "Hello, world!"], decision="allow")\n'
    )


def test_inserts_newline_when_missing_before_append(tmp_path):
    """Rust: codex-execpolicy/src/amend.rs inserts_newline_when_missing_before_append."""
    policy_path = tmp_path / "rules" / "default.rules"
    policy_path.parent.mkdir()
    policy_path.write_text('prefix_rule(pattern=["ls"], decision="allow")', encoding="utf-8")

    blocking_append_allow_prefix_rule(policy_path, ["echo", "Hello, world!"])

    assert policy_path.read_text(encoding="utf-8") == (
        'prefix_rule(pattern=["ls"], decision="allow")\n'
        'prefix_rule(pattern=["echo", "Hello, world!"], decision="allow")\n'
    )


def test_appends_network_rule(tmp_path):
    """Rust: codex-execpolicy/src/amend.rs appends_network_rule."""
    policy_path = tmp_path / "rules" / "default.rules"

    blocking_append_network_rule(
        policy_path,
        "Api.GitHub.com",
        NetworkRuleProtocol.HTTPS,
        Decision.ALLOW,
        "Allow https_connect access to api.github.com",
    )

    assert policy_path.read_text(encoding="utf-8") == (
        'network_rule(host="api.github.com", protocol="https", decision="allow", '
        'justification="Allow https_connect access to api.github.com")\n'
    )


def test_appends_prefix_and_network_rules(tmp_path):
    """Rust: codex-execpolicy/src/amend.rs appends_prefix_and_network_rules."""
    policy_path = tmp_path / "rules" / "default.rules"

    blocking_append_allow_prefix_rule(policy_path, ["curl"])
    blocking_append_network_rule(
        policy_path,
        "api.github.com",
        "https_connect",
        Decision.ALLOW,
        "Allow https_connect access to api.github.com",
    )

    assert policy_path.read_text(encoding="utf-8") == (
        'prefix_rule(pattern=["curl"], decision="allow")\n'
        'network_rule(host="api.github.com", protocol="https", decision="allow", '
        'justification="Allow https_connect access to api.github.com")\n'
    )


def test_rejects_wildcard_network_rule_host(tmp_path):
    """Rust: codex-execpolicy/src/amend.rs rejects_wildcard_network_rule_host."""
    policy_path = tmp_path / "rules" / "default.rules"

    with pytest.raises(AmendError) as excinfo:
        blocking_append_network_rule(
            policy_path,
            "*.example.com",
            NetworkRuleProtocol.HTTPS,
            Decision.ALLOW,
        )

    assert str(excinfo.value) == (
        "invalid network rule: invalid rule: network_rule host must be a specific host; "
        "wildcards are not allowed"
    )


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("Example.COM.", "example.com"),
        ("example.com:443", "example.com"),
        ("[2001:db8::1]:443", "2001:db8::1"),
    ],
)
def test_normalize_network_rule_host_accepts_rust_shapes(raw, normalized):
    """Rust: codex-execpolicy/src/rule.rs normalize_network_rule_host contract used by amend.rs."""
    assert normalize_network_rule_host(raw) == normalized


@pytest.mark.parametrize("justification", ["", "   "])
def test_rejects_empty_network_rule_justification(tmp_path, justification):
    """Rust: codex-execpolicy/src/amend.rs rejects empty justification before append."""
    with pytest.raises(AmendError, match="justification cannot be empty"):
        blocking_append_network_rule(
            tmp_path / "rules" / "default.rules",
            "api.github.com",
            NetworkRuleProtocol.HTTPS,
            Decision.ALLOW,
            justification,
        )
