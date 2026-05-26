"""Plaintext mention sigils shared by Codex crates.

This mirrors ``codex-rs/core/src/mention_syntax.rs`` and
``codex-rs/utils/plugins/src/mention_syntax.rs``.
"""

TOOL_MENTION_SIGIL = "$"
PLUGIN_TEXT_MENTION_SIGIL = "@"


__all__ = [
    "PLUGIN_TEXT_MENTION_SIGIL",
    "TOOL_MENTION_SIGIL",
]
