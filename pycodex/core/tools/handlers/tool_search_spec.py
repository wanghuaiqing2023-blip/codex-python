"""Tool-search tool spec facade.

Rust source:
``codex/codex-rs/core/src/tools/handlers/tool_search_spec.rs``.

The concrete Python schema builder lives with the tool-search handler because
Rust's handler and spec modules share the same deferred-search data contract.
This facade keeps the independent Rust spec coordinate explicit.
"""

from __future__ import annotations

from .tool_search import (
    TOOL_SEARCH_DEFAULT_LIMIT,
    TOOL_SEARCH_TOOL_NAME,
    create_tool_search_tool,
)

__all__ = [
    "TOOL_SEARCH_DEFAULT_LIMIT",
    "TOOL_SEARCH_TOOL_NAME",
    "create_tool_search_tool",
]
