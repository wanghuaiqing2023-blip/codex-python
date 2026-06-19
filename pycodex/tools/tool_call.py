"""Tool call boundary ported from ``codex-rs/tools``.

Rust defines ``ConversationHistory`` and ``ToolCall`` in ``codex-tools`` while
core routes and invokes them. The Python implementation lives in
``pycodex.core.tools.router`` alongside dispatch logic; this module exposes the
canonical tools-crate import path while preserving a single shared type.
"""

from pycodex.core.tools.router import ConversationHistory, ToolCall

__all__ = [
    "ConversationHistory",
    "ToolCall",
]
