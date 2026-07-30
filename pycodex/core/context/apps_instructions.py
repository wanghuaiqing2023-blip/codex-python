from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from pycodex.codex_mcp import CODEX_APPS_MCP_SERVER_NAME
from pycodex.protocol import APPS_INSTRUCTIONS_CLOSE_TAG, APPS_INSTRUCTIONS_OPEN_TAG

from .fragment import ContextualUserFragmentBase


def _field_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


@dataclass(frozen=True)
class AppsInstructions(ContextualUserFragmentBase):
    @classmethod
    def from_connectors(cls, connectors: Iterable[Any]) -> "AppsInstructions | None":
        for connector in connectors:
            if bool(_field_value(connector, "is_accessible", False)) and bool(
                _field_value(connector, "is_enabled", False)
            ):
                return cls()
        return None

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return APPS_INSTRUCTIONS_OPEN_TAG, APPS_INSTRUCTIONS_CLOSE_TAG

    def body(self) -> str:
        return (
            "\n## Apps (Connectors)\n"
            "Apps (Connectors) can be explicitly triggered in user messages in the format "
            "`[$app-name](app://{connector_id})`. Apps can also be implicitly triggered as long as the "
            "context suggests usage of available apps.\n"
            f"An app is equivalent to a set of MCP tools within the `{CODEX_APPS_MCP_SERVER_NAME}` MCP.\n"
            "An installed app's MCP tools are either provided to you already, or can be lazy-loaded through "
            "the `tool_search` tool. If `tool_search` is available, the apps that are searchable by "
            "`tools_search` will be listed by it.\n"
            "Do not additionally call list_mcp_resources or list_mcp_resource_templates for apps.\n"
        )


__all__ = ["AppsInstructions"]
