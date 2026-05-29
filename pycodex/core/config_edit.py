"""Small config edit engine ported from Codex core config editing."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex import _toml

from .features import FEATURES


CONFIG_TOML_FILE = "config.toml"
UPSTREAM_CONFIG_EDIT = "codex/codex-rs/core/src/config/edit.rs"


class ConfigEditError(ValueError):
    """Raised when a config edit cannot be applied."""


def _ensure_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ConfigEditError(f"{field} must be a string")
    return value


def _ensure_optional_str(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field)


def _ensure_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigEditError(f"{field} must be a bool")
    return value


def _ensure_i64(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigEditError(f"{field} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ConfigEditError(f"{field} is outside the i64 range")
    return value


def _ensure_u32(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigEditError(f"{field} must be an integer")
    if value < 0 or value > 2**32 - 1:
        raise ConfigEditError(f"{field} is outside the u32 range")
    return value


def _ensure_pathlike(value: object, field: str) -> str | os.PathLike[str]:
    if isinstance(value, (str, os.PathLike)):
        return value
    raise ConfigEditError(f"{field} must be path-like")


def _ensure_str_sequence(value: object, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ConfigEditError(f"{field} must be an iterable of strings")
    result = tuple(value)
    if not all(isinstance(item, str) for item in result):
        raise ConfigEditError(f"{field} must contain only strings")
    return result


def _ensure_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ConfigEditError(f"{field} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise ConfigEditError(f"{field} keys must be strings")
    return value


class ConfigEditKind(str, Enum):
    SET_PATH = "set_path"
    CLEAR_PATH = "clear_path"
    ADD_TOOL_SUGGEST_DISABLED_TOOL = "add_tool_suggest_disabled_tool"
    SET_SKILL_CONFIG = "set_skill_config"
    REPLACE_MCP_SERVERS = "replace_mcp_servers"


class SessionPickerViewMode(str, Enum):
    """Preferred layout for the resume/fork session picker."""

    COMFORTABLE = "comfortable"
    DENSE = "dense"

    @classmethod
    def default(cls) -> "SessionPickerViewMode":
        return cls.DENSE


class ToolSuggestDiscoverableType(str, Enum):
    CONNECTOR = "connector"
    PLUGIN = "plugin"


@dataclass(frozen=True)
class ToolSuggestDisabledTool:
    kind: ToolSuggestDiscoverableType | str
    id: str
    upstream_source: str = "codex/codex-rs/config/src/types.rs"

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _tool_suggest_type(self.kind))
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))

    @classmethod
    def plugin(cls, id: str) -> "ToolSuggestDisabledTool":
        return cls(ToolSuggestDiscoverableType.PLUGIN, id)

    @classmethod
    def connector(cls, id: str) -> "ToolSuggestDisabledTool":
        return cls(ToolSuggestDiscoverableType.CONNECTOR, id)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ToolSuggestDisabledTool | None":
        try:
            kind = _tool_suggest_type(value.get("type"))
        except ConfigEditError:
            return None
        id_value = value.get("id")
        if not isinstance(id_value, str):
            return None
        return cls(kind, id_value)

    def normalized(self) -> "ToolSuggestDisabledTool | None":
        trimmed = self.id.strip()
        if not trimmed:
            return None
        return ToolSuggestDisabledTool(self.kind, trimmed)

    def to_mapping(self) -> dict[str, str]:
        return {"type": self.kind.value, "id": self.id}


@dataclass(frozen=True)
class SkillConfigSelector:
    kind: str
    value: str

    def __post_init__(self) -> None:
        kind = _ensure_str(self.kind, "kind")
        if kind == "name":
            object.__setattr__(self, "value", _ensure_str(self.value, "name").strip())
        elif kind == "path":
            object.__setattr__(self, "value", normalize_skill_config_path(_ensure_pathlike(self.value, "path")))
        else:
            raise ConfigEditError(f"unknown skill config selector kind: {kind}")

    @classmethod
    def name(cls, name: str) -> "SkillConfigSelector":
        return cls("name", name)

    @classmethod
    def path(cls, path: str | Path) -> "SkillConfigSelector":
        return cls("path", path)


@dataclass(frozen=True)
class SkillConfigEdit:
    selector: SkillConfigSelector
    enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.selector, SkillConfigSelector):
            raise ConfigEditError("selector must be a SkillConfigSelector")
        object.__setattr__(self, "enabled", _ensure_bool(self.enabled, "enabled"))


@dataclass(frozen=True)
class ConfigEdit:
    kind: ConfigEditKind
    segments: tuple[str, ...]
    value: Any = None
    upstream_source: str = UPSTREAM_CONFIG_EDIT

    @classmethod
    def set_path(cls, segments: Iterable[str], value: Any) -> "ConfigEdit":
        return cls(ConfigEditKind.SET_PATH, _segments_tuple(segments), value)

    @classmethod
    def clear_path(cls, segments: Iterable[str]) -> "ConfigEdit":
        return cls(ConfigEditKind.CLEAR_PATH, _segments_tuple(segments))

    @classmethod
    def add_tool_suggest_disabled_tool(
        cls, disabled_tool: ToolSuggestDisabledTool | Mapping[str, Any]
    ) -> "ConfigEdit":
        return cls(
            ConfigEditKind.ADD_TOOL_SUGGEST_DISABLED_TOOL,
            ("tool_suggest", "disabled_tools"),
            _coerce_tool_suggest_disabled_tool(disabled_tool),
        )

    @classmethod
    def set_skill_config(cls, selector: SkillConfigSelector, enabled: bool) -> "ConfigEdit":
        return cls(
            ConfigEditKind.SET_SKILL_CONFIG,
            ("skills", "config"),
            SkillConfigEdit(_normalize_skill_config_selector(selector), _ensure_bool(enabled, "enabled")),
        )

    @classmethod
    def replace_mcp_servers(cls, servers: Mapping[str, Any]) -> "ConfigEdit":
        return cls(ConfigEditKind.REPLACE_MCP_SERVERS, ("mcp_servers",), dict(_ensure_mapping(servers, "servers")))


@dataclass
class ConfigEditsBuilder:
    codex_home: Path | None = None
    config_path: Path | None = None
    edits: list[ConfigEdit] = field(default_factory=list)

    @classmethod
    def new(cls, codex_home: str | Path) -> "ConfigEditsBuilder":
        return cls(codex_home=Path(codex_home))

    @classmethod
    def for_config_path(cls, config_path: str | Path) -> "ConfigEditsBuilder":
        return cls(config_path=Path(config_path))

    def set_model(self, model: str | None, effort: str | Enum | None = None) -> "ConfigEditsBuilder":
        self.edits.extend(model_selection_edits(model, effort))
        return self

    def set_service_tier(self, service_tier: str | Enum | None) -> "ConfigEditsBuilder":
        self.edits.append(service_tier_edit(service_tier))
        return self

    def set_personality(self, personality: str | Enum | None) -> "ConfigEditsBuilder":
        self.edits.append(personality_edit(personality))
        return self

    def set_hide_full_access_warning(self, acknowledged: bool) -> "ConfigEditsBuilder":
        self.edits.append(notice_hide_full_access_warning_edit(acknowledged))
        return self

    def set_hide_world_writable_warning(self, acknowledged: bool) -> "ConfigEditsBuilder":
        self.edits.append(notice_hide_world_writable_warning_edit(acknowledged))
        return self

    def set_hide_rate_limit_model_nudge(self, acknowledged: bool) -> "ConfigEditsBuilder":
        self.edits.append(notice_hide_rate_limit_model_nudge_edit(acknowledged))
        return self

    def set_hide_model_migration_prompt(self, model: str, acknowledged: bool) -> "ConfigEditsBuilder":
        self.edits.append(notice_hide_model_migration_prompt_edit(model, acknowledged))
        return self

    def set_hide_external_config_migration_prompt_home(self, acknowledged: bool) -> "ConfigEditsBuilder":
        self.edits.append(notice_hide_external_config_migration_prompt_home_edit(acknowledged))
        return self

    def set_hide_external_config_migration_prompt_project(
        self, project: str, acknowledged: bool
    ) -> "ConfigEditsBuilder":
        self.edits.append(notice_hide_external_config_migration_prompt_project_edit(project, acknowledged))
        return self

    def record_model_migration_seen(self, from_model: str, to_model: str) -> "ConfigEditsBuilder":
        self.edits.append(record_model_migration_seen_edit(from_model, to_model))
        return self

    def add_tool_suggest_disabled_tool(
        self, disabled_tool: ToolSuggestDisabledTool | Mapping[str, Any]
    ) -> "ConfigEditsBuilder":
        self.edits.append(add_tool_suggest_disabled_tool_edit(disabled_tool))
        return self

    def set_project_trust_level(self, project_path: str | Path, trust_level: str | Enum) -> "ConfigEditsBuilder":
        self.edits.append(project_trust_level_edit(project_path, trust_level))
        return self

    def set_skill_config(self, path: str | Path, enabled: bool) -> "ConfigEditsBuilder":
        self.edits.append(set_skill_config_edit(path, enabled))
        return self

    def set_skill_config_by_name(self, name: str, enabled: bool) -> "ConfigEditsBuilder":
        self.edits.append(set_skill_config_by_name_edit(name, enabled))
        return self

    def replace_mcp_servers(self, servers: Mapping[str, Any]) -> "ConfigEditsBuilder":
        self.edits.append(replace_mcp_servers_edit(servers))
        return self

    def set_feature_enabled(self, key: str, enabled: bool) -> "ConfigEditsBuilder":
        self.edits.append(set_feature_enabled_edit(key, enabled))
        return self

    def set_model_availability_nux_count(self, shown_count: Mapping[str, int]) -> "ConfigEditsBuilder":
        self.edits.extend(model_availability_nux_count_edits(shown_count))
        return self

    def set_windows_sandbox_mode(self, mode: str) -> "ConfigEditsBuilder":
        self.edits.append(windows_sandbox_mode_edit(mode))
        return self

    def set_realtime_microphone(self, microphone: str | None) -> "ConfigEditsBuilder":
        self.edits.append(realtime_microphone_edit(microphone))
        return self

    def set_realtime_speaker(self, speaker: str | None) -> "ConfigEditsBuilder":
        self.edits.append(realtime_speaker_edit(speaker))
        return self

    def set_realtime_voice(self, voice: str | None) -> "ConfigEditsBuilder":
        self.edits.append(realtime_voice_edit(voice))
        return self

    def clear_legacy_windows_sandbox_keys(self) -> "ConfigEditsBuilder":
        self.edits.extend(clear_legacy_windows_sandbox_key_edits())
        return self

    def set_session_picker_view(self, mode: SessionPickerViewMode | str) -> "ConfigEditsBuilder":
        self.edits.append(session_picker_view_edit(mode))
        return self

    def with_edits(self, edits: Iterable[ConfigEdit]) -> "ConfigEditsBuilder":
        self.edits.extend(edits)
        return self

    def resolved_config_path(self) -> Path:
        if self.config_path is not None:
            return self.config_path
        if self.codex_home is None:
            raise ConfigEditError("codex_home or config_path is required")
        return self.codex_home / CONFIG_TOML_FILE

    def apply_blocking(self) -> bool:
        return apply_blocking_to_resolved_file(self.resolved_config_path(), self.edits)

    async def apply(self) -> bool:
        return await asyncio.to_thread(self.apply_blocking)


def model_selection_edits(model: str | None, effort: str | Enum | None = None) -> list[ConfigEdit]:
    return [
        _optional_string_edit(("model",), model),
        _optional_string_edit(("model_reasoning_effort",), _string_value(effort) if effort is not None else None),
    ]


def service_tier_edit(service_tier: str | Enum | None) -> ConfigEdit:
    if service_tier is None:
        return ConfigEdit.clear_path(("service_tier",))
    value = _service_tier_config_value(_string_value(service_tier))
    return ConfigEdit.set_path(("service_tier",), value)


def personality_edit(personality: str | Enum | None) -> ConfigEdit:
    return _optional_string_edit(("personality",), _string_value(personality) if personality is not None else None)


def syntax_theme_edit(name: str) -> ConfigEdit:
    return ConfigEdit.set_path(("tui", "theme"), str(name))


def tui_pet_edit(name: str) -> ConfigEdit:
    return ConfigEdit.set_path(("tui", "pet"), str(name))


def session_picker_view_edit(mode: SessionPickerViewMode | str) -> ConfigEdit:
    return ConfigEdit.set_path(("tui", "session_picker_view"), _string_value(mode))


def status_line_items_edit(items: Iterable[str]) -> ConfigEdit:
    return ConfigEdit.set_path(("tui", "status_line"), list(_ensure_str_sequence(items, "items")))

def status_line_use_colors_edit(enabled: bool) -> ConfigEdit:
    return ConfigEdit.set_path(("tui", "status_line_use_colors"), _ensure_bool(enabled, "enabled"))

def terminal_title_items_edit(items: Iterable[str]) -> ConfigEdit:
    return ConfigEdit.set_path(("tui", "terminal_title"), list(_ensure_str_sequence(items, "items")))

def keymap_bindings_edit(context: str, action: str, keys: Iterable[str]) -> ConfigEdit:
    keys_tuple = _ensure_str_sequence(keys, "keys")
    value: str | list[str]
    if len(keys_tuple) == 1:
        value = keys_tuple[0]
    else:
        value = list(keys_tuple)
    return ConfigEdit.set_path(("tui", "keymap", _ensure_str(context, "context"), _ensure_str(action, "action")), value)

def keymap_binding_edit(context: str, action: str, key: str) -> ConfigEdit:
    return keymap_bindings_edit(context, action, (_ensure_str(key, "key"),))

def keymap_binding_clear_edit(context: str, action: str) -> ConfigEdit:
    return ConfigEdit.clear_path(("tui", "keymap", _ensure_str(context, "context"), _ensure_str(action, "action")))

def model_availability_nux_count_edits(shown_count: Mapping[str, int]) -> list[ConfigEdit]:
    shown = _ensure_mapping(shown_count, "shown_count")
    edits = [ConfigEdit.clear_path(("tui", "model_availability_nux"))]
    for model_slug, count in sorted(shown.items()):
        edits.append(ConfigEdit.set_path(("tui", "model_availability_nux", model_slug), _ensure_u32(count, f"shown_count[{model_slug!r}]")))
    return edits

def notice_hide_full_access_warning_edit(acknowledged: bool) -> ConfigEdit:
    return ConfigEdit.set_notice_hide_full_access_warning(_ensure_bool(acknowledged, "acknowledged"))

def notice_hide_world_writable_warning_edit(acknowledged: bool) -> ConfigEdit:
    return ConfigEdit.set_notice_hide_world_writable_warning(_ensure_bool(acknowledged, "acknowledged"))

def notice_hide_rate_limit_model_nudge_edit(acknowledged: bool) -> ConfigEdit:
    return ConfigEdit.set_notice_hide_rate_limit_model_nudge(_ensure_bool(acknowledged, "acknowledged"))

def notice_hide_model_migration_prompt_edit(model_prompt_key: str, acknowledged: bool) -> ConfigEdit:
    return ConfigEdit.set_notice_hide_model_migration_prompt(_ensure_str(model_prompt_key, "model_prompt_key"), _ensure_bool(acknowledged, "acknowledged"))

def notice_hide_external_config_migration_prompt_home_edit(acknowledged: bool) -> ConfigEdit:
    return ConfigEdit.set_notice_hide_external_config_migration_prompt_home(_ensure_bool(acknowledged, "acknowledged"))

def notice_external_config_migration_prompt_home_last_prompted_at_edit(timestamp: int) -> ConfigEdit:
    return ConfigEdit.set_notice_external_config_migration_prompt_home_last_prompted_at(_ensure_i64(timestamp, "timestamp"))

def notice_hide_external_config_migration_prompt_project_edit(project: str, acknowledged: bool) -> ConfigEdit:
    return ConfigEdit.set_notice_hide_external_config_migration_prompt_project(_ensure_str(project, "project"), _ensure_bool(acknowledged, "acknowledged"))

def notice_external_config_migration_prompt_project_last_prompted_at_edit(project: str, timestamp: int) -> ConfigEdit:
    return ConfigEdit.set_notice_external_config_migration_prompt_project_last_prompted_at(_ensure_str(project, "project"), _ensure_i64(timestamp, "timestamp"))

def record_model_migration_seen_edit(from_model: str, to_model: str) -> ConfigEdit:
    return ConfigEdit.record_model_migration_seen(_ensure_str(from_model, "from_model"), _ensure_str(to_model, "to_model"))

def add_tool_suggest_disabled_tool_edit(disabled_tool: ToolSuggestDisabledTool | Mapping[str, Any]) -> ConfigEdit:
    return ConfigEdit.add_tool_suggest_disabled_tool(disabled_tool)


def project_trust_level_edit(project_path: str | Path, trust_level: str | Enum) -> ConfigEdit:
    return ConfigEdit.set_path(
        ("projects", project_trust_key(project_path), "trust_level"),
        _project_trust_level_value(trust_level),
    )


def project_trust_key(project_path: str | Path) -> str:
    path = Path(project_path)
    resolved = path.resolve(strict=False)
    normalized = str(resolved if str(resolved) else path)
    if os.name == "nt":
        return normalized.lower()
    return normalized


def set_skill_config_edit(path: str | Path, enabled: bool) -> ConfigEdit:
    return ConfigEdit.set_skill_config(SkillConfigSelector.path(path), enabled)


def set_skill_config_by_name_edit(name: str, enabled: bool) -> ConfigEdit:
    return ConfigEdit.set_skill_config(SkillConfigSelector.name(name), enabled)


def replace_mcp_servers_edit(servers: Mapping[str, Any]) -> ConfigEdit:
    return ConfigEdit.replace_mcp_servers(servers)


def normalize_skill_config_path(path: str | Path) -> str:
    target = Path(path)
    try:
        return str(target.resolve(strict=True))
    except (OSError, RuntimeError):
        return str(target)


def set_feature_enabled_edit(key: str, enabled: bool) -> ConfigEdit:
    segments = ("features", key)
    is_default_false_feature = any(spec.key == key and not spec.default_enabled for spec in FEATURES)
    if enabled or not is_default_false_feature:
        return ConfigEdit.set_path(segments, bool(enabled))
    return ConfigEdit.clear_path(segments)


def windows_sandbox_mode_edit(mode: str) -> ConfigEdit:
    return ConfigEdit.set_path(("windows", "sandbox"), str(mode))


def realtime_microphone_edit(microphone: str | None) -> ConfigEdit:
    return _optional_string_edit(("audio", "microphone"), microphone)


def realtime_speaker_edit(speaker: str | None) -> ConfigEdit:
    return _optional_string_edit(("audio", "speaker"), speaker)


def realtime_voice_edit(voice: str | None) -> ConfigEdit:
    return _optional_string_edit(("realtime", "voice"), voice)


def clear_legacy_windows_sandbox_key_edits() -> list[ConfigEdit]:
    return [
        ConfigEdit.clear_path(("features", "experimental_windows_sandbox")),
        ConfigEdit.clear_path(("features", "elevated_windows_sandbox")),
        ConfigEdit.clear_path(("features", "enable_experimental_windows_sandbox")),
    ]


def apply_config_edit(config: MutableMapping[str, Any], edit: ConfigEdit) -> bool:
    if edit.kind is ConfigEditKind.SET_PATH:
        return _insert(config, edit.segments, edit.value)
    if edit.kind is ConfigEditKind.CLEAR_PATH:
        return _remove(config, edit.segments)
    if edit.kind is ConfigEditKind.ADD_TOOL_SUGGEST_DISABLED_TOOL:
        return _add_tool_suggest_disabled_tool(config, _coerce_tool_suggest_disabled_tool(edit.value))
    if edit.kind is ConfigEditKind.SET_SKILL_CONFIG:
        return _set_skill_config(config, _coerce_skill_config_edit(edit.value))
    if edit.kind is ConfigEditKind.REPLACE_MCP_SERVERS:
        if not isinstance(edit.value, Mapping):
            raise ConfigEditError("mcp_servers must be a mapping")
        return _replace_mcp_servers(config, edit.value)
    raise ConfigEditError(f"unsupported config edit kind: {edit.kind}")


def apply_config_edits(config: MutableMapping[str, Any], edits: Iterable[ConfigEdit]) -> bool:
    mutated = False
    for edit in edits:
        mutated = apply_config_edit(config, edit) or mutated
    return mutated


def apply_blocking(codex_home: str | Path, edits: Iterable[ConfigEdit]) -> bool:
    return apply_blocking_to_resolved_file(Path(codex_home) / CONFIG_TOML_FILE, edits)


async def apply(codex_home: str | Path, edits: Iterable[ConfigEdit]) -> bool:
    return await asyncio.to_thread(apply_blocking, codex_home, tuple(edits))


def apply_blocking_to_resolved_file(config_path: str | Path, edits: Iterable[ConfigEdit]) -> bool:
    edits = tuple(edits)
    if not edits:
        return False

    path = Path(config_path)
    config = read_toml_mapping(path)
    mutated = apply_config_edits(config, edits)
    if not mutated:
        return False

    write_toml_mapping(path, config)
    return True


def read_toml_mapping(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    with target.open("rb") as file:
        return dict(_toml.load(file))


def write_toml_mapping(path: str | Path, config: MutableMapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    contents = dumps_toml_mapping(config)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(contents, encoding="utf-8", newline="\n")
    os.replace(temporary, target)


def dumps_toml_mapping(config: MutableMapping[str, Any]) -> str:
    lines: list[str] = []
    _append_table_lines(lines, (), config)
    return "\n".join(lines).rstrip() + "\n"


def _insert(config: MutableMapping[str, Any], segments: tuple[str, ...], value: Any) -> bool:
    if not segments:
        return False

    parent = _descend(config, segments[:-1], create=True)
    if parent is None:
        return False

    key = segments[-1]
    if parent.get(key) == value:
        return False
    parent[key] = value
    return True


def _remove(config: MutableMapping[str, Any], segments: tuple[str, ...]) -> bool:
    if not segments:
        return False

    parent = _descend(config, segments[:-1], create=False)
    if parent is None:
        return False
    return parent.pop(segments[-1], None) is not None


def _add_tool_suggest_disabled_tool(
    config: MutableMapping[str, Any],
    disabled_tool: ToolSuggestDisabledTool,
) -> bool:
    existing_item = config.get("tool_suggest")
    existing_table = existing_item if isinstance(existing_item, MutableMapping) else {}
    existing_disabled = existing_table.get("disabled_tools")

    disabled_tools: list[ToolSuggestDisabledTool] = []
    seen: set[ToolSuggestDisabledTool] = set()
    for candidate in _iter_tool_suggest_disabled_tools(existing_disabled):
        normalized = candidate.normalized()
        if normalized is not None and normalized not in seen:
            seen.add(normalized)
            disabled_tools.append(normalized)

    normalized_new = disabled_tool.normalized()
    if normalized_new is not None and normalized_new not in seen:
        disabled_tools.append(normalized_new)

    value = [tool.to_mapping() for tool in disabled_tools]
    return _insert(config, ("tool_suggest", "disabled_tools"), value)


def _set_skill_config(config: MutableMapping[str, Any], edit: SkillConfigEdit) -> bool:
    selector = _normalize_skill_config_selector(edit.selector)
    if selector.kind == "name" and not selector.value:
        return False

    skills = config.get("skills")
    if edit.enabled:
        if not isinstance(skills, MutableMapping):
            return False
        entries = skills.get("config")
        if not isinstance(entries, list):
            return False
        index = _find_skill_config_entry(entries, selector)
        if index is None:
            return False
        entries.pop(index)
        if not entries:
            skills.pop("config", None)
            if not skills:
                config.pop("skills", None)
        return True

    if not isinstance(skills, MutableMapping):
        skills = {}
        config["skills"] = skills

    entries = skills.get("config")
    if not isinstance(entries, list):
        entries = []
        skills["config"] = entries

    index = _find_skill_config_entry(entries, selector)
    new_entry = _skill_config_entry_for_selector(selector)
    new_entry["enabled"] = False
    if index is None:
        entries.append(new_entry)
        return True

    existing = entries[index]
    if isinstance(existing, Mapping):
        replacement = dict(existing)
        _write_skill_config_selector(replacement, selector)
        replacement["enabled"] = False
    else:
        replacement = new_entry
    if replacement == existing:
        return False
    entries[index] = replacement
    return True


def _replace_mcp_servers(config: MutableMapping[str, Any], servers: Mapping[str, Any]) -> bool:
    if not servers:
        return _remove(config, ("mcp_servers",))

    serialized = {
        str(name): _serialize_mcp_server(server)
        for name, server in sorted(servers.items(), key=lambda item: str(item[0]))
    }
    return _insert(config, ("mcp_servers",), serialized)


def _serialize_mcp_server(config: Any) -> dict[str, Any]:
    transport = _field(config, "transport")
    kind = str(_field(transport, "kind", "")).lower()
    entry: dict[str, Any] = {}

    if kind == "stdio":
        command = _field(transport, "command")
        if command is not None:
            entry["command"] = str(command)
        args = tuple(_field(transport, "args", ()) or ())
        if args:
            entry["args"] = [str(arg) for arg in args]
        env = _field(transport, "env")
        if isinstance(env, Mapping) and env:
            entry["env"] = {str(key): str(value) for key, value in sorted(env.items(), key=lambda item: str(item[0]))}
        env_vars = tuple(_field(transport, "env_vars", ()) or ())
        if env_vars:
            entry["env_vars"] = [str(value) for value in env_vars]
        cwd = _field(transport, "cwd")
        if cwd is not None:
            entry["cwd"] = str(cwd)
    elif kind in {"streamable_http", "streamablehttp"}:
        url = _field(transport, "url")
        if url is not None:
            entry["url"] = str(url)
        bearer = _field(transport, "bearer_token_env_var")
        if bearer is not None:
            entry["bearer_token_env_var"] = str(bearer)
        http_headers = _field(transport, "http_headers")
        if isinstance(http_headers, Mapping) and http_headers:
            entry["http_headers"] = {
                str(key): str(value) for key, value in sorted(http_headers.items(), key=lambda item: str(item[0]))
            }
        env_http_headers = _field(transport, "env_http_headers")
        if isinstance(env_http_headers, Mapping) and env_http_headers:
            entry["env_http_headers"] = {
                str(key): str(value) for key, value in sorted(env_http_headers.items(), key=lambda item: str(item[0]))
            }
    else:
        raise ConfigEditError(f"unsupported MCP server transport kind: {kind!r}")

    if not bool(_field(config, "enabled", True)):
        entry["enabled"] = False
    environment_id = _field(config, "environment_id", "local")
    if environment_id not in (None, "local"):
        entry["environment_id"] = str(environment_id)
    if bool(_field(config, "required", False)):
        entry["required"] = True
    if bool(_field(config, "supports_parallel_tool_calls", False)):
        entry["supports_parallel_tool_calls"] = True

    for key in ("startup_timeout_sec", "tool_timeout_sec"):
        value = _field(config, key)
        if value is not None:
            entry[key] = float(value)

    approval_mode = _field(config, "default_tools_approval_mode")
    if approval_mode is not None:
        entry["default_tools_approval_mode"] = _string_value(approval_mode)

    for key in ("enabled_tools", "disabled_tools", "scopes"):
        values = tuple(_field(config, key, ()) or ())
        if values:
            entry[key] = [str(value) for value in values]

    oauth = _field(config, "oauth")
    client_id = _field(oauth, "client_id") if oauth is not None else None
    if client_id:
        entry["oauth"] = {"client_id": str(client_id)}
    oauth_resource = _field(config, "oauth_resource")
    if oauth_resource:
        entry["oauth_resource"] = str(oauth_resource)

    tools = _field(config, "tools", {}) or {}
    if isinstance(tools, Mapping) and tools:
        entry["tools"] = _serialize_mcp_server_tools(tools)

    return entry


def _serialize_mcp_server_tools(tools: Mapping[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for name, tool_config in sorted(tools.items(), key=lambda item: str(item[0])):
        approval_mode = _field(tool_config, "approval_mode")
        serialized_tool: dict[str, Any] = {}
        if approval_mode is not None:
            serialized_tool["approval_mode"] = _string_value(approval_mode)
        serialized[str(name)] = serialized_tool
    return serialized


def _find_skill_config_entry(entries: list[Any], selector: SkillConfigSelector) -> int | None:
    for index, entry in enumerate(entries):
        if _skill_config_selector_from_entry(entry) == selector:
            return index
    return None


def _skill_config_selector_from_entry(entry: Any) -> SkillConfigSelector | None:
    if not isinstance(entry, Mapping):
        return None
    path = entry.get("path")
    name = entry.get("name")
    has_path = isinstance(path, str)
    has_name = isinstance(name, str)
    if has_path == has_name:
        return None
    if has_path:
        return SkillConfigSelector.path(path)
    trimmed = str(name).strip()
    if not trimmed:
        return None
    return SkillConfigSelector.name(trimmed)


def _skill_config_entry_for_selector(selector: SkillConfigSelector) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    _write_skill_config_selector(entry, selector)
    return entry


def _write_skill_config_selector(entry: MutableMapping[str, Any], selector: SkillConfigSelector) -> None:
    if selector.kind == "name":
        entry.pop("path", None)
        entry["name"] = selector.value
    elif selector.kind == "path":
        entry.pop("name", None)
        entry["path"] = selector.value
    else:
        raise ConfigEditError(f"invalid skill config selector kind: {selector.kind!r}")


def _iter_tool_suggest_disabled_tools(value: Any) -> Iterable[ToolSuggestDisabledTool]:
    if not isinstance(value, list):
        return ()

    tools: list[ToolSuggestDisabledTool] = []
    for item in value:
        if isinstance(item, Mapping):
            parsed = ToolSuggestDisabledTool.from_mapping(item)
            if parsed is not None:
                tools.append(parsed)
    return tools


def _descend(
    config: MutableMapping[str, Any],
    segments: tuple[str, ...],
    *,
    create: bool,
) -> MutableMapping[str, Any] | None:
    current = config
    for segment in segments:
        value = current.get(segment)
        if value is None:
            if not create:
                return None
            value = {}
            current[segment] = value
        if not isinstance(value, MutableMapping):
            if not create:
                return None
            value = {}
            current[segment] = value
        current = value
    return current


def _append_table_lines(lines: list[str], path: tuple[str, ...], table: MutableMapping[str, Any]) -> None:
    array_table_items = [
        (key, value) for key, value in table.items() if _should_emit_array_of_tables(path, str(key), value)
    ]
    scalar_items = [
        (key, value)
        for key, value in table.items()
        if not isinstance(value, MutableMapping) and not _should_emit_array_of_tables(path, str(key), value)
    ]
    child_tables = [(key, value) for key, value in table.items() if isinstance(value, MutableMapping)]

    should_emit_header = bool(path) and (bool(scalar_items) or (not child_tables and not array_table_items))
    if should_emit_header:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[{'.'.join(_quote_key(part) for part in path)}]")

    for key, value in scalar_items:
        lines.append(f"{_quote_key(str(key))} = {_toml_value(value)}")

    for key, value in array_table_items:
        _append_array_of_tables_lines(lines, (*path, str(key)), value)

    for key, value in child_tables:
        _append_table_lines(lines, (*path, str(key)), value)


def _should_emit_array_of_tables(path: tuple[str, ...], key: str, value: Any) -> bool:
    return path == ("skills",) and key == "config" and isinstance(value, list) and all(
        isinstance(item, Mapping) for item in value
    )


def _append_array_of_tables_lines(lines: list[str], path: tuple[str, ...], values: list[Any]) -> None:
    for value in values:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[[{'.'.join(_quote_key(part) for part in path)}]]")
        for key, item in value.items():
            if isinstance(item, Mapping):
                raise ConfigEditError(f"unsupported nested array-of-tables value: {item!r}")
            lines.append(f"{_quote_key(str(key))} = {_toml_value(item)}")


def _toml_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return _toml_value(_string_value(value))
    if isinstance(value, Mapping):
        _ensure_mapping(value, "value")
        items = ", ".join(f"{_quote_key(str(key))} = {_toml_value(item)}" for key, item in value.items())
        return f"{{ {items} }}"
    if isinstance(value, tuple):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, str):
        return f'"{_escape_basic_string(value)}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if value is None:
        return '""'
    raise ConfigEditError(f"unsupported TOML value type: {type(value).__name__}")

def _quote_key(key: str) -> str:
    if key.replace("_", "").replace("-", "").isalnum() and key:
        return key
    return f'"{_escape_basic_string(key)}"'


def _escape_basic_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\b", "\\b")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\f", "\\f")
        .replace("\r", "\\r")
    )


def _string_value(value: object) -> str:
    if isinstance(value, Enum):
        enum_value = value.value
        if not isinstance(enum_value, str):
            raise ConfigEditError("enum value must be a string")
        return enum_value
    return _ensure_str(value, "value")

def _optional_string_edit(segments: tuple[str, ...], value: str | None) -> ConfigEdit:
    string_value = _ensure_optional_str(value, "value")
    if string_value is None:
        return ConfigEdit.clear_path(segments)
    return ConfigEdit.set_path(segments, string_value)

def _coerce_tool_suggest_disabled_tool(value: ToolSuggestDisabledTool | Mapping[str, Any]) -> ToolSuggestDisabledTool:
    if isinstance(value, ToolSuggestDisabledTool):
        return value
    if isinstance(value, Mapping):
        parsed = ToolSuggestDisabledTool.from_mapping(value)
        if parsed is not None:
            return parsed
    raise ConfigEditError(f"invalid tool_suggest disabled tool: {value!r}")


def _coerce_skill_config_edit(value: SkillConfigEdit | Mapping[str, Any]) -> SkillConfigEdit:
    if isinstance(value, SkillConfigEdit):
        return value
    if isinstance(value, Mapping):
        selector = value.get("selector")
        enabled = value.get("enabled")
        if isinstance(selector, Mapping):
            selector = SkillConfigSelector(_ensure_str(selector.get("kind"), "selector.kind"), selector.get("value"))
        if not isinstance(selector, SkillConfigSelector):
            raise ConfigEditError("selector must be a SkillConfigSelector")
        return SkillConfigEdit(selector, _ensure_bool(enabled, "enabled"))
    raise ConfigEditError("invalid skill config edit")

def _normalize_skill_config_selector(selector: SkillConfigSelector) -> SkillConfigSelector:
    if selector.kind == "name":
        return SkillConfigSelector.name(selector.value)
    if selector.kind == "path":
        return SkillConfigSelector.path(selector.value)
    raise ConfigEditError(f"invalid skill config selector kind: {selector.kind!r}")


def _tool_suggest_type(value: ToolSuggestDiscoverableType | str) -> ToolSuggestDiscoverableType:
    if isinstance(value, ToolSuggestDiscoverableType):
        return value
    if not isinstance(value, str):
        raise ConfigEditError("tool suggest type must be a string")
    try:
        return ToolSuggestDiscoverableType(value)
    except ValueError as exc:
        raise ConfigEditError(f"unknown tool suggest type: {value}") from exc

def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _project_trust_level_value(value: str | Enum) -> str:
    resolved = _string_value(value)
    if resolved not in {"trusted", "untrusted"}:
        raise ConfigEditError(f"invalid project trust level: {value!r}")
    return resolved


def _service_tier_config_value(value: str) -> str:
    if value in {"fast", "priority"}:
        return "fast"
    if value == "flex":
        return "flex"
    return value


def _segments_tuple(segments: Iterable[str]) -> tuple[str, ...]:
    result = _ensure_str_sequence(segments, "segments")
    if not result:
        raise ConfigEditError("config edit path must not be empty")
    return result

