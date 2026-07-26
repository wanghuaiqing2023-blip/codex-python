"""Tool specification for the Rust ``request_plugin_install_spec`` module."""

from __future__ import annotations

from typing import Any

from pycodex.tools.tool_discovery import (
    LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME,
    REQUEST_PLUGIN_INSTALL_TOOL_NAME,
)

JsonValue = Any


def create_request_plugin_install_tool() -> dict[str, JsonValue]:
    description = (
        "# Request plugin/connector install\n\n"
        f"Use this tool only after `{LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME}` returns a plugin or connector that exactly matches the user's explicit request.\n\n"
        "Do not use it for adjacent capabilities, broad recommendations, or tools that merely seem useful. "
        "Pass the returned `tool_type` through directly, and pass the returned `id` as `tool_id`.\n\n"
        "IMPORTANT: DO NOT call this tool in parallel with other tools."
    )
    return {
        "type": "function",
        "name": REQUEST_PLUGIN_INSTALL_TOOL_NAME,
        "description": description,
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "description": 'Type of discoverable tool to suggest. Use "connector" or "plugin".',
                },
                "action_type": {
                    "type": "string",
                    "description": 'Suggested action for the tool. Use "install".',
                },
                "tool_id": {
                    "type": "string",
                    "description": "Connector or plugin id to suggest.",
                },
                "suggest_reason": {
                    "type": "string",
                    "description": "Concise one-line user-facing reason why this plugin or connector can help with the current request.",
                },
            },
            "required": ["tool_type", "action_type", "tool_id", "suggest_reason"],
            "additionalProperties": False,
        },
    }


__all__ = ["create_request_plugin_install_tool"]
