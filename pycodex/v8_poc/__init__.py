"""Proof-of-concept V8 facade for Rust crate ``codex-v8-poc``.

The upstream crate is a tiny Bazel-wired V8 smoke-test crate. PyCodex keeps the
public contract dependency-light: it exposes the stable label and feature
queries, plus small standard-library helpers used to mirror the Rust test
contracts without embedding V8.
"""

from __future__ import annotations

import ast
import json
import os
from dataclasses import dataclass
from typing import Any

BAZEL_TARGET = "//codex-rs/v8-poc:v8-poc"
_DEFAULT_EMBEDDED_V8_VERSION = "python-v8-poc-compatible"


def bazel_target() -> str:
    """Return the Bazel label for this proof-of-concept crate."""

    return BAZEL_TARGET


def embedded_v8_version() -> str:
    """Return a non-empty embedded-engine version marker.

    Rust returns ``v8::V8::get_version()``. The Python port intentionally does
    not bundle V8, so this returns an overrideable non-empty compatibility
    marker while preserving the public non-empty-string contract.
    """

    return os.environ.get("PYCODEX_EMBEDDED_V8_VERSION", _DEFAULT_EMBEDDED_V8_VERSION) or _DEFAULT_EMBEDDED_V8_VERSION


def linked_v8_has_sandbox() -> bool:
    """Return whether this Python facade is configured as sandbox-enabled."""

    return _env_flag("PYCODEX_V8_POC_SANDBOX")


def evaluate_expression(expression: str) -> str:
    """Evaluate the tiny expression subset covered by Rust smoke tests.

    This helper is intentionally limited to string and integer constants with
    ``+``. It is not a JavaScript engine.
    """

    if not isinstance(expression, str):
        raise TypeError("expression must be a string")
    node = ast.parse(expression, mode="eval")
    value = _eval_allowed_expression(node.body)
    return str(value)


def json_to_cbor_dispatchable(message: bytes | str) -> "Dispatchable":
    """Mirror the Rust test path ``v8::crdtp::json_to_cbor`` enough for parity."""

    if isinstance(message, bytes):
        message = message.decode("utf-8")
    if not isinstance(message, str):
        raise TypeError("message must be bytes or str")
    try:
        decoded = json.loads(message)
    except json.JSONDecodeError as exc:
        return Dispatchable(None, error=str(exc))
    return Dispatchable(decoded)


@dataclass(frozen=True)
class Dispatchable:
    payload: dict[str, Any] | None
    error: str | None = None

    def ok(self) -> bool:
        return self.error is None and isinstance(self.payload, dict)

    def call_id(self) -> int | None:
        if not self.ok():
            return None
        value = self.payload.get("id")  # type: ignore[union-attr]
        return value if isinstance(value, int) else None

    def method(self) -> bytes | None:
        if not self.ok():
            return None
        value = self.payload.get("method")  # type: ignore[union-attr]
        return value.encode("utf-8") if isinstance(value, str) else None


def _eval_allowed_expression(node: ast.AST) -> int | str:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, str)):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _eval_allowed_expression(node.left)
        right = _eval_allowed_expression(node.right)
        if isinstance(left, int) and isinstance(right, int):
            return left + right
        if isinstance(left, str) and isinstance(right, str):
            return left + right
    raise ValueError("unsupported expression for v8-poc facade")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


__all__ = [
    "BAZEL_TARGET",
    "Dispatchable",
    "bazel_target",
    "embedded_v8_version",
    "evaluate_expression",
    "json_to_cbor_dispatchable",
    "linked_v8_has_sandbox",
]
