"""Parity tests for Rust ``codex-login::auth::util``.

Rust source:
- ``codex/codex-rs/login/src/auth/util.rs``
"""

from __future__ import annotations

from pycodex.login.auth.util import try_parse_error_message


def test_try_parse_error_message_extracts_openai_error_message() -> None:
    text = """{
  "error": {
    "message": "Your refresh token has already been used to generate a new access token. Please try signing in again.",
    "type": "invalid_request_error",
    "param": null,
    "code": "refresh_token_reused"
  }
}"""

    assert (
        try_parse_error_message(text)
        == "Your refresh token has already been used to generate a new access token. Please try signing in again."
    )


def test_try_parse_error_message_falls_back_to_raw_text() -> None:
    text = '{"message": "test"}'

    assert try_parse_error_message(text) == text


def test_try_parse_error_message_falls_back_for_invalid_json() -> None:
    assert try_parse_error_message("not json") == "not json"


def test_try_parse_error_message_empty_text_is_unknown_error() -> None:
    assert try_parse_error_message("") == "Unknown error"


def test_try_parse_error_message_requires_nested_string_message() -> None:
    assert try_parse_error_message('{"error": {"message": 123}}') == '{"error": {"message": 123}}'
    assert try_parse_error_message('{"error": "bad"}') == '{"error": "bad"}'
