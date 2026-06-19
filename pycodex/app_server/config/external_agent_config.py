"""External-agent config migration helpers.

Ported from ``app-server/src/config/external_agent_config.rs``. This module
keeps the dependency-light pieces of the migration service: data shapes,
settings merging, plugin-source discovery, text rewriting, and config value
projection. File-system migration and marketplace installation remain runtime
boundaries.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

EXTERNAL_AGENT_CONFIG_DETECT_METRIC = "codex.external_agent_config.detect"
EXTERNAL_AGENT_CONFIG_IMPORT_METRIC = "codex.external_agent_config.import"
EXTERNAL_AGENT_DIR = ".claude"
EXTERNAL_AGENT_CONFIG_MD = "CLAUDE.md"
EXTERNAL_OFFICIAL_MARKETPLACE_NAME = "claude-plugins-official"
EXTERNAL_OFFICIAL_MARKETPLACE_SOURCE = "anthropics/claude-plugins-official"


@dataclass(frozen=True)
class ExternalAgentConfigDetectOptions:
    include_home: bool
    cwds: tuple[Path, ...] | None = None


class ExternalAgentConfigMigrationItemType(Enum):
    CONFIG = "Config"
    SKILLS = "Skills"
    AGENTS_MD = "AgentsMd"
    PLUGINS = "Plugins"
    MCP_SERVER_CONFIG = "McpServerConfig"
    SUBAGENTS = "Subagents"
    HOOKS = "Hooks"
    COMMANDS = "Commands"
    SESSIONS = "Sessions"


@dataclass(frozen=True)
class PluginsMigration:
    marketplace_name: str
    plugin_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class NamedMigration:
    name: str


@dataclass(frozen=True)
class MigrationDetails:
    plugins: tuple[PluginsMigration, ...] = ()
    sessions: tuple[Any, ...] = ()
    mcp_servers: tuple[NamedMigration, ...] = ()
    hooks: tuple[NamedMigration, ...] = ()
    subagents: tuple[NamedMigration, ...] = ()
    commands: tuple[NamedMigration, ...] = ()


@dataclass(frozen=True)
class PendingPluginImport:
    cwd: Path | None
    details: MigrationDetails


@dataclass(frozen=True)
class PluginImportOutcome:
    succeeded_marketplaces: tuple[str, ...] = ()
    succeeded_plugin_ids: tuple[str, ...] = ()
    failed_marketplaces: tuple[str, ...] = ()
    failed_plugin_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExternalAgentConfigMigrationItem:
    item_type: ExternalAgentConfigMigrationItemType
    description: str
    cwd: Path | None = None
    details: MigrationDetails | None = None


@dataclass(frozen=True)
class MarketplaceImportSource:
    source: str
    ref_name: str | None = None


@dataclass
class ExternalAgentConfigService:
    codex_home: Path
    external_agent_home: Path = field(default_factory=lambda: default_external_agent_home())

    @classmethod
    def new(cls, codex_home: Path | str) -> "ExternalAgentConfigService":
        return cls(Path(codex_home))

    @classmethod
    def new_for_test(
        cls,
        codex_home: Path | str,
        external_agent_home: Path | str,
    ) -> "ExternalAgentConfigService":
        return cls(Path(codex_home), Path(external_agent_home))

    def external_agent_session_source_path(self, path: Path | str) -> Path | None:
        candidate = Path(path)
        if candidate.suffix != ".jsonl":
            return None
        try:
            resolved = candidate.resolve(strict=True)
            projects_root = (self.external_agent_home / "projects").resolve(strict=True)
        except FileNotFoundError:
            return None
        return resolved if _is_relative_to(resolved, projects_root) else None

    async def detect(self, _params: ExternalAgentConfigDetectOptions) -> list[ExternalAgentConfigMigrationItem]:
        raise NotImplementedError("real external-agent detection is a runtime boundary")

    async def import_(self, _migration_items: list[ExternalAgentConfigMigrationItem]) -> list[PendingPluginImport]:
        raise NotImplementedError("real external-agent import is a runtime boundary")


def default_external_agent_home(env: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if env is None else env
    home = environment.get("HOME") or environment.get("USERPROFILE")
    return Path(home) / EXTERNAL_AGENT_DIR if home else Path(EXTERNAL_AGENT_DIR)


def merge_json_settings(existing: Any, incoming: Any) -> Any:
    if isinstance(existing, dict) and isinstance(incoming, Mapping):
        for key, incoming_value in incoming.items():
            if key in existing:
                existing[key] = merge_json_settings(existing[key], incoming_value)
            else:
                existing[key] = _deep_copy_json(incoming_value)
        return existing
    return _deep_copy_json(incoming)


def collect_enabled_plugins(settings: Mapping[str, Any] | Any) -> list[str]:
    enabled_plugins = settings.get("enabledPlugins") if isinstance(settings, Mapping) else None
    if not isinstance(enabled_plugins, Mapping):
        return []
    plugins: list[str] = []
    for plugin_key, enabled in enabled_plugins.items():
        if enabled is True and _parse_plugin_id(str(plugin_key)) is not None:
            plugins.append(str(plugin_key))
    return plugins


def has_enabled_plugin_for_marketplace(settings: Mapping[str, Any] | Any, marketplace_name: str) -> bool:
    for plugin_id in collect_enabled_plugins(settings):
        parsed = _parse_plugin_id(plugin_id)
        if parsed is not None and parsed[1] == marketplace_name:
            return True
    return False


def collect_marketplace_import_sources(
    settings: Mapping[str, Any] | Any,
    source_root: Path | str,
) -> dict[str, MarketplaceImportSource]:
    result: dict[str, MarketplaceImportSource] = {}
    source_root_path = Path(source_root)
    extra = settings.get("extraKnownMarketplaces") if isinstance(settings, Mapping) else None
    if isinstance(extra, Mapping):
        for name, value in extra.items():
            if not isinstance(value, Mapping):
                continue
            source_fields = value.get("source") if isinstance(value.get("source"), Mapping) else value
            if not isinstance(source_fields, Mapping):
                continue
            source = (
                source_fields.get("repo")
                or source_fields.get("url")
                or source_fields.get("path")
                or value.get("source")
            )
            if not isinstance(source, str):
                source = str(source) if source is not None else ""
            source = source.strip()
            if not source:
                continue
            ref_name = source_fields.get("ref", value.get("ref"))
            ref_name = ref_name.strip() if isinstance(ref_name, str) and ref_name.strip() else None
            result[str(name)] = MarketplaceImportSource(
                source=resolve_external_marketplace_source(source, source_root_path),
                ref_name=ref_name,
            )

    if (
        has_enabled_plugin_for_marketplace(settings, EXTERNAL_OFFICIAL_MARKETPLACE_NAME)
        and EXTERNAL_OFFICIAL_MARKETPLACE_NAME not in result
    ):
        result[EXTERNAL_OFFICIAL_MARKETPLACE_NAME] = MarketplaceImportSource(
            source=EXTERNAL_OFFICIAL_MARKETPLACE_SOURCE,
            ref_name=None,
        )
    return dict(sorted(result.items()))


def resolve_external_marketplace_source(source: str, source_root: Path | str) -> str:
    if not looks_like_relative_local_path(source):
        return source
    return str(Path(source_root) / source)


def looks_like_relative_local_path(source: str) -> bool:
    return source.startswith("./") or source.startswith("../") or source in {".", ".."}


def rewrite_external_agent_terms(content: str) -> str:
    rewritten = replace_case_insensitive_with_boundaries(
        content,
        EXTERNAL_AGENT_CONFIG_MD.lower(),
        "AGENTS.md",
    )
    for source in ("claude code", "claude-code", "claude_code", "claudecode", "claude"):
        rewritten = replace_case_insensitive_with_boundaries(rewritten, source, "Codex")
    return rewritten


def replace_case_insensitive_with_boundaries(input_text: str, needle: str, replacement: str) -> str:
    needle_lower = needle.lower()
    if not needle_lower:
        return input_text
    haystack_lower = input_text.lower()
    output: list[str] = []
    last_emitted = 0
    search_start = 0
    matched = False
    while True:
        start = haystack_lower.find(needle_lower, search_start)
        if start == -1:
            break
        end = start + len(needle_lower)
        boundary_before = start == 0 or not is_word_byte(input_text[start - 1])
        boundary_after = end == len(input_text) or not is_word_byte(input_text[end])
        if boundary_before and boundary_after:
            output.append(input_text[last_emitted:start])
            output.append(replacement)
            last_emitted = end
            matched = True
        search_start = start + 1
    if not matched:
        return input_text
    output.append(input_text[last_emitted:])
    return "".join(output)


def is_word_byte(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char == "_")


def build_config_from_external(settings: Mapping[str, Any] | Any) -> dict[str, Any]:
    if not isinstance(settings, Mapping):
        raise ValueError("external agent settings root must be an object")
    root: dict[str, Any] = {}
    env = settings.get("env")
    if isinstance(env, Mapping) and env:
        env_table = json_object_to_env_toml_table(env)
        if env_table:
            root["shell_environment_policy"] = {
                "inherit": "core",
                "set": env_table,
            }
    sandbox = settings.get("sandbox")
    if isinstance(sandbox, Mapping) and sandbox.get("enabled") is True:
        root["sandbox_mode"] = "workspace-write"
    return root


def json_object_to_env_toml_table(object_value: Mapping[str, Any]) -> dict[str, str]:
    table: dict[str, str] = {}
    for key, value in object_value.items():
        string_value = json_env_value_to_string(value)
        if string_value is not None:
            table[str(key)] = string_value
    return table


def json_env_value_to_string(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def merge_missing_toml_values(existing: dict[str, Any], incoming: Mapping[str, Any]) -> bool:
    if not isinstance(existing, dict) or not isinstance(incoming, Mapping):
        raise ValueError("expected TOML table while merging migrated config values")
    changed = False
    for key, incoming_value in incoming.items():
        if key in existing:
            if isinstance(existing[key], dict) and isinstance(incoming_value, Mapping):
                changed = merge_missing_toml_values(existing[key], incoming_value) or changed
        else:
            existing[key] = _deep_copy_json(incoming_value)
            changed = True
    return changed


def migrated_mcp_server_names(value: Mapping[str, Any] | Any) -> list[str]:
    servers = value.get("mcp_servers") if isinstance(value, Mapping) else None
    return sorted(str(name) for name in servers.keys()) if isinstance(servers, Mapping) else []


def named_migrations(names: list[str]) -> list[NamedMigration]:
    return [NamedMigration(name) for name in names]


def is_empty_toml_table(value: Any) -> bool:
    return isinstance(value, Mapping) and not value


def migration_metric_tags(
    item_type: ExternalAgentConfigMigrationItemType,
    skills_count: int | None = None,
) -> list[tuple[str, str]]:
    migration_type = {
        ExternalAgentConfigMigrationItemType.CONFIG: "config",
        ExternalAgentConfigMigrationItemType.SKILLS: "skills",
        ExternalAgentConfigMigrationItemType.AGENTS_MD: "agents_md",
        ExternalAgentConfigMigrationItemType.PLUGINS: "plugins",
        ExternalAgentConfigMigrationItemType.MCP_SERVER_CONFIG: "mcp_server_config",
        ExternalAgentConfigMigrationItemType.SUBAGENTS: "subagents",
        ExternalAgentConfigMigrationItemType.HOOKS: "hooks",
        ExternalAgentConfigMigrationItemType.COMMANDS: "commands",
        ExternalAgentConfigMigrationItemType.SESSIONS: "sessions",
    }[item_type]
    tags = [("migration_type", migration_type)]
    if item_type in {
        ExternalAgentConfigMigrationItemType.SKILLS,
        ExternalAgentConfigMigrationItemType.SUBAGENTS,
        ExternalAgentConfigMigrationItemType.COMMANDS,
    }:
        tags.append(("skills_count", str(skills_count or 0)))
    return tags


def _parse_plugin_id(plugin_id: str) -> tuple[str, str] | None:
    if plugin_id.count("@") != 1:
        return None
    plugin_name, marketplace_name = plugin_id.split("@", 1)
    if not plugin_name or not marketplace_name:
        return None
    return plugin_name, marketplace_name


def _deep_copy_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _deep_copy_json(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_deep_copy_json(child) for child in value]
    return value


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


__all__ = [
    "EXTERNAL_AGENT_CONFIG_DETECT_METRIC",
    "EXTERNAL_AGENT_CONFIG_IMPORT_METRIC",
    "EXTERNAL_AGENT_CONFIG_MD",
    "EXTERNAL_AGENT_DIR",
    "EXTERNAL_OFFICIAL_MARKETPLACE_NAME",
    "EXTERNAL_OFFICIAL_MARKETPLACE_SOURCE",
    "ExternalAgentConfigDetectOptions",
    "ExternalAgentConfigMigrationItem",
    "ExternalAgentConfigMigrationItemType",
    "ExternalAgentConfigService",
    "MarketplaceImportSource",
    "MigrationDetails",
    "NamedMigration",
    "PendingPluginImport",
    "PluginImportOutcome",
    "PluginsMigration",
    "build_config_from_external",
    "collect_enabled_plugins",
    "collect_marketplace_import_sources",
    "default_external_agent_home",
    "has_enabled_plugin_for_marketplace",
    "is_empty_toml_table",
    "json_env_value_to_string",
    "json_object_to_env_toml_table",
    "looks_like_relative_local_path",
    "merge_json_settings",
    "merge_missing_toml_values",
    "migrated_mcp_server_names",
    "migration_metric_tags",
    "named_migrations",
    "replace_case_insensitive_with_boundaries",
    "resolve_external_marketplace_source",
    "rewrite_external_agent_terms",
]
