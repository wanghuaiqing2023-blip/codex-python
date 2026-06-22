from __future__ import annotations

from pycodex.utils.plugins.mention_syntax import (
    PLUGIN_TEXT_MENTION_SIGIL,
    TOOL_MENTION_SIGIL,
)


def test_tool_mention_sigil_is_dollar() -> None:
    # Source: codex/codex-rs/utils/plugins/src/mention_syntax.rs
    # Contract: default plaintext sigil for tools is `$`.
    assert TOOL_MENTION_SIGIL == "$"


def test_plugin_text_mention_sigil_is_at() -> None:
    # Source: codex/codex-rs/utils/plugins/src/mention_syntax.rs
    # Contract: plugins use `@` in linked plaintext outside TUI.
    assert PLUGIN_TEXT_MENTION_SIGIL == "@"
