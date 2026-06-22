from __future__ import annotations

import pytest

from pycodex.v8_poc import (
    bazel_target,
    embedded_v8_version,
    evaluate_expression,
    json_to_cbor_dispatchable,
    linked_v8_has_sandbox,
)


def test_exposes_expected_bazel_target() -> None:
    # Rust source: codex-v8-poc/src/lib.rs::tests::exposes_expected_bazel_target.
    assert bazel_target() == "//codex-rs/v8-poc:v8-poc"


def test_exposes_embedded_v8_version() -> None:
    # Rust source: codex-v8-poc/src/lib.rs::tests::exposes_embedded_v8_version.
    assert embedded_v8_version()


def test_sandbox_feature_matches_default_linked_v8() -> None:
    # Rust source: codex-v8-poc/src/lib.rs::tests::sandbox_feature_matches_linked_v8.
    assert linked_v8_has_sandbox() is False


def test_sandbox_feature_can_be_enabled_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYCODEX_V8_POC_SANDBOX", "true")
    assert linked_v8_has_sandbox() is True


def test_evaluates_integer_addition() -> None:
    # Rust source: codex-v8-poc/src/lib.rs::tests::evaluates_integer_addition.
    assert evaluate_expression("1 + 2") == "3"


def test_evaluates_string_concatenation() -> None:
    # Rust source: codex-v8-poc/src/lib.rs::tests::evaluates_string_concatenation.
    assert evaluate_expression("'hello ' + 'world'") == "hello world"


def test_rejects_unsupported_expression() -> None:
    with pytest.raises(ValueError, match="unsupported expression"):
        evaluate_expression("Math.max(1, 2)")


def test_parses_crdtp_dispatchable_messages() -> None:
    # Rust source: codex-v8-poc/src/lib.rs::tests::parses_crdtp_dispatchable_messages.
    dispatchable = json_to_cbor_dispatchable(b'{"id":7,"method":"Runtime.evaluate","params":{}}')
    assert dispatchable.ok()
    assert dispatchable.call_id() == 7
    assert dispatchable.method() == b"Runtime.evaluate"
