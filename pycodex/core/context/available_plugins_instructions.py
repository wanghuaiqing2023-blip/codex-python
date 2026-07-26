from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from pycodex.plugin import PluginCapabilitySummary
from pycodex.protocol import PLUGINS_INSTRUCTIONS_CLOSE_TAG, PLUGINS_INSTRUCTIONS_OPEN_TAG

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class AvailablePluginsInstructions(ContextualUserFragmentBase):
    plugins: tuple[PluginCapabilitySummary, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "plugins",
            tuple(PluginCapabilitySummary.from_value(plugin) for plugin in self.plugins),
        )

    @classmethod
    def from_plugins(
        cls,
        plugins: Iterable[PluginCapabilitySummary | Mapping[str, Any] | Any],
    ) -> "AvailablePluginsInstructions | None":
        items = tuple(PluginCapabilitySummary.from_value(plugin) for plugin in plugins)
        return cls(items) if items else None

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return PLUGINS_INSTRUCTIONS_OPEN_TAG, PLUGINS_INSTRUCTIONS_CLOSE_TAG

    def body(self) -> str:
        lines = [
            "## Plugins",
            "A plugin is a local bundle of skills, MCP servers, and apps. Below is the list of plugins that "
            "are enabled and available in this session.",
            "### Available plugins",
        ]
        for plugin in self.plugins:
            if plugin.description is None:
                lines.append(f"- `{plugin.display_name}`")
            else:
                lines.append(f"- `{plugin.display_name}`: {plugin.description}")
        lines.append("### How to use plugins")
        lines.append(
            "- Discovery: The list above is the plugins available in this session.\n"
            "- Skill naming: If a plugin contributes skills, those skill entries are prefixed with "
            "`plugin_name:` in the Skills list.\n"
            "- Trigger rules: If the user explicitly names a plugin, prefer capabilities associated with "
            "that plugin for that turn.\n"
            "- Relationship to capabilities: Plugins are not invoked directly. Use their underlying skills, "
            "MCP tools, and app tools to help solve the task.\n"
            "- Preference: When a relevant plugin is available, prefer using capabilities associated with "
            "that plugin over standalone capabilities that provide similar functionality.\n"
            "- Missing/blocked: If the user requests a plugin that is not listed above, or the plugin does not "
            "have relevant callable capabilities for the task, say so briefly and continue with the best fallback."
        )
        joined = "\n".join(lines)
        return f"\n{joined}\n"


__all__ = ["AvailablePluginsInstructions"]
