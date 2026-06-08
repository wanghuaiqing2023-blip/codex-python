"""Core plugin modules aligned with ``codex-rs/core/src/plugins``."""

from pycodex.core.context import PluginCapabilitySummary
from pycodex.core.skills import build_skill_name_counts

from .mentions import (
    APP_PATH_PREFIX,
    MCP_PATH_PREFIX,
    PLUGIN_PATH_PREFIX,
    SKILL_FILENAME,
    SKILL_PATH_PREFIX,
    CollectedToolMentions,
    ToolMentionKind,
    ToolMentions,
    app_id_from_path,
    build_connector_slug_counts,
    collect_explicit_app_ids,
    collect_explicit_plugin_mentions,
    collect_tool_mentions_from_messages,
    collect_tool_mentions_from_messages_with_sigil,
    extract_tool_mentions,
    extract_tool_mentions_with_sigil,
    is_skill_filename,
    normalize_skill_path,
    plugin_config_name_from_path,
    tool_kind_for_path,
)
from .discoverable import (
    TOOL_SUGGEST_DISCOVERABLE_MARKETPLACE_ALLOWLIST,
    list_tool_suggest_discoverable_plugins,
)
from .injection import build_plugin_injections
from .render import render_explicit_plugin_instructions

__all__ = [
    "APP_PATH_PREFIX",
    "MCP_PATH_PREFIX",
    "PLUGIN_PATH_PREFIX",
    "PluginCapabilitySummary",
    "SKILL_FILENAME",
    "SKILL_PATH_PREFIX",
    "CollectedToolMentions",
    "TOOL_SUGGEST_DISCOVERABLE_MARKETPLACE_ALLOWLIST",
    "ToolMentionKind",
    "ToolMentions",
    "app_id_from_path",
    "build_plugin_injections",
    "build_connector_slug_counts",
    "build_skill_name_counts",
    "collect_explicit_app_ids",
    "collect_explicit_plugin_mentions",
    "collect_tool_mentions_from_messages",
    "collect_tool_mentions_from_messages_with_sigil",
    "extract_tool_mentions",
    "extract_tool_mentions_with_sigil",
    "is_skill_filename",
    "list_tool_suggest_discoverable_plugins",
    "normalize_skill_path",
    "plugin_config_name_from_path",
    "render_explicit_plugin_instructions",
    "tool_kind_for_path",
]


def __getattr__(name: str):
    if name == "test_support":
        from importlib import import_module

        return import_module("pycodex.core.plugins.test_support")
    raise AttributeError(name)
