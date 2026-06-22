"""Rust-derived tests for codex-execpolicy/src/error.rs."""

from __future__ import annotations

from pycodex.execpolicy import (
    ErrorLocation,
    ExampleDidMatchError,
    ExampleDidNotMatchError,
    InvalidDecisionError,
    InvalidExampleError,
    InvalidPatternError,
    InvalidRuleError,
    TextPosition,
    TextRange,
)


def _location() -> ErrorLocation:
    return ErrorLocation(
        path="policy.star",
        range=TextRange(
            start=TextPosition(line=2, column=3),
            end=TextPosition(line=2, column=9),
        ),
    )


def test_text_position_range_and_location_are_value_objects():
    """Rust: TextPosition, TextRange, and ErrorLocation are copy/equality structs."""
    assert _location() == ErrorLocation(
        path="policy.star",
        range=TextRange(
            start=TextPosition(line=2, column=3),
            end=TextPosition(line=2, column=9),
        ),
    )


def test_simple_error_messages_match_rust_display_text():
    """Rust: Error Display text for InvalidDecision/Pattern/Example/Rule variants."""
    assert str(InvalidDecisionError("invalid decision: deny")) == "invalid decision: deny"
    assert str(InvalidPatternError("prefix cannot be empty")) == "invalid pattern element: prefix cannot be empty"
    assert str(InvalidExampleError("not a command")) == "invalid example: not a command"
    assert str(InvalidRuleError("network_rule host cannot be empty")) == (
        "invalid rule: network_rule host cannot be empty"
    )


def test_example_did_not_match_message_and_location_attachment():
    """Rust: ExampleDidNotMatch Display and with_location fill missing location."""
    err = ExampleDidNotMatchError(["PrefixRule { echo }"], ["echo hi", "ls"])

    assert str(err) == (
        'expected every example to match at least one rule. rules: ["PrefixRule { echo }"]; '
        'unmatched examples: ["echo hi", "ls"]'
    )
    assert err.location() is None

    located = err.with_location(_location())
    assert located is not err
    assert located.location() == _location()
    assert located.with_location(ErrorLocation(path="other", range=_location().range)) is located


def test_example_did_match_message_and_location_attachment():
    """Rust: ExampleDidMatch Display and with_location fill missing location."""
    err = ExampleDidMatchError("PrefixRule { rm }", "rm -rf /tmp")

    assert str(err) == "expected example to not match rule `PrefixRule { rm }`: rm -rf /tmp"
    assert err.location() is None

    located = err.with_location(_location())
    assert located is not err
    assert located.location() == _location()
    assert located.with_location(ErrorLocation(path="other", range=_location().range)) is located


def test_non_example_errors_ignore_with_location_like_rust():
    """Rust: Error::with_location only annotates example-match variants."""
    err = InvalidPatternError("bad")
    assert err.with_location(_location()) is err
    assert err.location() is None
