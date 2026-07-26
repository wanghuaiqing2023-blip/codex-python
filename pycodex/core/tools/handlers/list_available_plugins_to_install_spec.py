"""Tool specification for listing installable plugins and connectors."""

from __future__ import annotations

from typing import Any

from pycodex.core.tools.handlers.tool_search import TOOL_SEARCH_TOOL_NAME
from pycodex.tools.tool_discovery import (
    LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME,
    REQUEST_PLUGIN_INSTALL_TOOL_NAME,
)

JsonValue = Any


def create_list_available_plugins_to_install_tool() -> dict[str, JsonValue]:
    description = (
        "# List plugin/connector install candidates\n\n"
        "Use this tool only when both are true:\n"
        "- The user explicitly asks to use a specific plugin or connector that is not already available in the current context or active `tools` list.\n"
        f"- `{TOOL_SEARCH_TOOL_NAME}` is not available, or it has already been called and did not find or make the requested tool callable.\n\n"
        f"Returns known plugins and connectors that can be passed to `{REQUEST_PLUGIN_INSTALL_TOOL_NAME}`. "
        "When both a plugin and a connector match, prefer the plugin; use the connector only when its corresponding plugin is already installed.\n"
    )
    return {
        "type": "function",
        "name": LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME,
        "description": description,
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    }


__all__ = ["create_list_available_plugins_to_install_tool"]
