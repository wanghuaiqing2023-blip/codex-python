"""Function call error boundary ported from ``codex-rs/tools``.

Rust defines ``FunctionCallError`` in ``codex-tools`` and core re-exports it.
The Python runtime already uses the shared implementation in
``pycodex.core.function_tool``; this module provides the canonical tools-crate
import path without creating a second error type.
"""

from pycodex.core.function_tool import FunctionCallError, FunctionCallErrorKind

__all__ = [
    "FunctionCallError",
    "FunctionCallErrorKind",
]
