"""Re-exports matching codex-core's ``mention_syntax`` module."""

from pycodex.utils.plugins.mention_syntax import PLUGIN_TEXT_MENTION_SIGIL
from pycodex.utils.plugins.mention_syntax import TOOL_MENTION_SIGIL


__all__ = [
    "PLUGIN_TEXT_MENTION_SIGIL",
    "TOOL_MENTION_SIGIL",
]
