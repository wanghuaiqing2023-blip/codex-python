"""Rust-derived tests for codex-execpolicy/src/decision.rs."""

from __future__ import annotations

import pytest

from pycodex.execpolicy import Decision, InvalidDecisionError, strongest_decision


def test_decision_parse_accepts_rust_policy_strings():
    """Rust: Decision::parse accepts allow, prompt, and forbidden."""
    assert Decision.parse("allow") is Decision.ALLOW
    assert Decision.parse("prompt") is Decision.PROMPT
    assert Decision.parse("forbidden") is Decision.FORBIDDEN


def test_decision_parse_rejects_unknown_value_with_rust_error_text():
    """Rust: Decision::parse returns Error::InvalidDecision for other strings."""
    with pytest.raises(InvalidDecisionError) as excinfo:
        Decision.parse("deny")

    assert str(excinfo.value) == "invalid decision: deny"


def test_decision_string_values_match_rust_camel_case_serialization():
    """Rust: Decision derives Serialize/Deserialize with rename_all = camelCase."""
    assert Decision.ALLOW.value == "allow"
    assert Decision.PROMPT.value == "prompt"
    assert Decision.FORBIDDEN.value == "forbidden"


def test_decision_ordering_contract_is_allow_prompt_forbidden():
    """Rust: derived Ord orders enum variants Allow < Prompt < Forbidden."""
    assert strongest_decision([Decision.ALLOW, Decision.PROMPT]) is Decision.PROMPT
    assert strongest_decision([Decision.ALLOW, Decision.PROMPT, Decision.FORBIDDEN]) is Decision.FORBIDDEN
