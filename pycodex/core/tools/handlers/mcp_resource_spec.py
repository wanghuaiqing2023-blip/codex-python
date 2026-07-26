"""Tool specifications for the Rust ``mcp_resource_spec`` module."""

from __future__ import annotations

from typing import Any

JsonValue = Any

LIST_MCP_RESOURCES_TOOL_NAME = "list_mcp_resources"
LIST_MCP_RESOURCE_TEMPLATES_TOOL_NAME = "list_mcp_resource_templates"
READ_MCP_RESOURCE_TOOL_NAME = "read_mcp_resource"


def create_list_mcp_resources_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": LIST_MCP_RESOURCES_TOOL_NAME,
        "description": "Lists resources provided by MCP servers. Resources allow servers to share data that provides context to language models, such as files, database schemas, or application-specific information. Prefer resources over web search when possible.",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Optional MCP server name. When omitted, lists resources from every configured server."},
                "cursor": {"type": "string", "description": "Opaque cursor returned by a previous list_mcp_resources call for the same server."},
            },
            "additionalProperties": False,
        },
    }


def create_list_mcp_resource_templates_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": LIST_MCP_RESOURCE_TEMPLATES_TOOL_NAME,
        "description": "Lists resource templates provided by MCP servers. Parameterized resource templates allow servers to share data that takes parameters and provides context to language models, such as files, database schemas, or application-specific information. Prefer resource templates over web search when possible.",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Optional MCP server name. When omitted, lists resource templates from all configured servers."},
                "cursor": {"type": "string", "description": "Opaque cursor returned by a previous list_mcp_resource_templates call for the same server."},
            },
            "additionalProperties": False,
        },
    }


def create_read_mcp_resource_tool() -> dict[str, JsonValue]:
    return {
        "type": "function",
        "name": READ_MCP_RESOURCE_TOOL_NAME,
        "description": "Read a specific resource from an MCP server given the server name and resource URI.",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "MCP server name exactly as configured. Must match the 'server' field returned by list_mcp_resources."},
                "uri": {"type": "string", "description": "Resource URI to read. Must be one of the URIs returned by list_mcp_resources."},
            },
            "required": ["server", "uri"],
            "additionalProperties": False,
        },
    }


__all__ = [
    "LIST_MCP_RESOURCES_TOOL_NAME",
    "LIST_MCP_RESOURCE_TEMPLATES_TOOL_NAME",
    "READ_MCP_RESOURCE_TOOL_NAME",
    "create_list_mcp_resource_templates_tool",
    "create_list_mcp_resources_tool",
    "create_read_mcp_resource_tool",
]
