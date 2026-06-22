"""Prepared parity tests for Rust ``codex-secrets/src/sanitizer.rs``.

Pytest is deferred until the full ``codex-secrets`` crate is functionally
complete, per the crate-level porting workflow.
"""

from __future__ import annotations

from pycodex.secrets.sanitizer import REDACTED_SECRET, redact_secrets


def test_load_regex_accepts_plain_secret_text() -> None:
    # Rust source: sanitizer.rs load_regex compiles all regexes through redact_secrets("secret").
    assert redact_secrets("secret") == "secret"


def test_redacts_openai_and_aws_key_patterns() -> None:
    # Rust source: OPENAI_KEY_REGEX and AWS_ACCESS_KEY_ID_REGEX.
    text = "openai=sk-1234567890ABCDEFGHIJKLMNOP aws=AKIA1234567890ABCDEF"

    assert redact_secrets(text) == f"openai={REDACTED_SECRET} aws={REDACTED_SECRET}"


def test_redacts_bearer_token_case_insensitively() -> None:
    # Rust source: BEARER_TOKEN_REGEX uses (?i) and normalizes replacement to "Bearer".
    text = "authorization: bearer abcdefghijklmnop.qrs-tuv_123"

    assert redact_secrets(text) == f"authorization: Bearer {REDACTED_SECRET}"


def test_redacts_secret_assignments_preserving_key_separator_and_quote() -> None:
    # Rust source: SECRET_ASSIGNMENT_REGEX replacement preserves groups $1, $2, and $3.
    text = "api_key = 'abcdefghijklmnop' token: 123456789 password=\"supersecretvalue\""

    assert redact_secrets(text) == (
        f"api_key = '{REDACTED_SECRET}' "
        f"token: {REDACTED_SECRET} "
        f"password=\"{REDACTED_SECRET}\""
    )
