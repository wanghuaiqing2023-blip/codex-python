"""Plugin utility helpers ported from `codex-rs/utils/plugins`."""

from .mcp_connector import (
    DISALLOWED_CONNECTOR_IDS,
    FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS,
    is_connector_id_allowed,
    sanitize_name,
)
from .mention_syntax import PLUGIN_TEXT_MENTION_SIGIL, TOOL_MENTION_SIGIL
from .plugin_namespace import (
    DISCOVERABLE_PLUGIN_MANIFEST_PATHS,
    PluginSkillRoot,
    find_plugin_manifest_path,
    plugin_namespace_for_skill_path,
)

__all__ = [
    "DISALLOWED_CONNECTOR_IDS",
    "DISCOVERABLE_PLUGIN_MANIFEST_PATHS",
    "FIRST_PARTY_CHAT_DISALLOWED_CONNECTOR_IDS",
    "PLUGIN_TEXT_MENTION_SIGIL",
    "PluginSkillRoot",
    "TOOL_MENTION_SIGIL",
    "find_plugin_manifest_path",
    "is_connector_id_allowed",
    "plugin_namespace_for_skill_path",
    "sanitize_name",
]
