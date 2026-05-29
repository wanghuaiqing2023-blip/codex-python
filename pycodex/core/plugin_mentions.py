"""Explicit app/plugin mention collection ported from Codex.

This mirrors the dependency-free behavior in
``codex-rs/core/src/plugins/mentions.rs`` and the shared mention parser from
``codex-rs/core-skills/src/injection.rs``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.core.connectors import connector_name_slug
from pycodex.core.context import PluginCapabilitySummary
from pycodex.core.mention_syntax import (
    PLUGIN_TEXT_MENTION_SIGIL,
    TOOL_MENTION_SIGIL,
)
from pycodex.core.tool_discovery import AppInfo

JsonValue = Any

APP_PATH_PREFIX = "app://"
MCP_PATH_PREFIX = "mcp://"
PLUGIN_PATH_PREFIX = "plugin://"
SKILL_PATH_PREFIX = "skill://"
SKILL_FILENAME = "SKILL.md"

_COMMON_ENV_VARS = frozenset(
    {
        "HOME",
        "LANG",
        "PATH",
        "PWD",
        "SHELL",
        "TEMP",
        "TERM",
        "TMP",
        "TMPDIR",
        "USER",
        "XDG_CONFIG_HOME",
    }
)


class ToolMentionKind(str, Enum):
    APP = "app"
    MCP = "mcp"
    PLUGIN = "plugin"
    SKILL = "skill"
    OTHER = "other"


@dataclass(frozen=True)
class ToolMentions:
    names: frozenset[str]
    paths: frozenset[str]
    plain_names: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "names", _ensure_str_frozenset(self.names, "names"))
        object.__setattr__(self, "paths", _ensure_str_frozenset(self.paths, "paths"))
        object.__setattr__(self, "plain_names", _ensure_str_frozenset(self.plain_names, "plain_names"))

    def is_empty(self) -> bool:
        return not self.names and not self.paths


@dataclass(frozen=True)
class CollectedToolMentions:
    plain_names: frozenset[str]
    paths: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "plain_names", _ensure_str_frozenset(self.plain_names, "plain_names"))
        object.__setattr__(self, "paths", _ensure_str_frozenset(self.paths, "paths"))


def tool_kind_for_path(path: str | Path) -> ToolMentionKind:
    _ensure_str(path, "path")
    value = path
    if value.startswith(APP_PATH_PREFIX):
        return ToolMentionKind.APP
    if value.startswith(MCP_PATH_PREFIX):
        return ToolMentionKind.MCP
    if value.startswith(PLUGIN_PATH_PREFIX):
        return ToolMentionKind.PLUGIN
    if value.startswith(SKILL_PATH_PREFIX) or is_skill_filename(value):
        return ToolMentionKind.SKILL
    return ToolMentionKind.OTHER


def is_skill_filename(path: str | Path) -> bool:
    _ensure_str(path, "path")
    file_name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return file_name.lower() == SKILL_FILENAME.lower()


def app_id_from_path(path: str | Path) -> str | None:
    _ensure_str(path, "path")
    value = path
    if not value.startswith(APP_PATH_PREFIX):
        return None
    app_id = value[len(APP_PATH_PREFIX) :]
    return app_id or None


def plugin_config_name_from_path(path: str | Path) -> str | None:
    _ensure_str(path, "path")
    value = path
    if not value.startswith(PLUGIN_PATH_PREFIX):
        return None
    config_name = value[len(PLUGIN_PATH_PREFIX) :]
    return config_name or None


def normalize_skill_path(path: str | Path) -> str:
    _ensure_str(path, "path")
    value = path
    if value.startswith(SKILL_PATH_PREFIX):
        return value[len(SKILL_PATH_PREFIX) :]
    return value


def extract_tool_mentions(text: str) -> ToolMentions:
    _ensure_str(text, "text")
    return extract_tool_mentions_with_sigil(text, TOOL_MENTION_SIGIL)


def extract_tool_mentions_with_sigil(text: str, sigil: str) -> ToolMentions:
    _ensure_str(text, "text")
    _ensure_str(sigil, "sigil")
    if len(sigil) != 1:
        raise ValueError("sigil must be a single character")

    mentioned_names: set[str] = set()
    mentioned_paths: set[str] = set()
    plain_names: set[str] = set()

    index = 0
    while index < len(text):
        character = text[index]
        if character == "[":
            parsed = _parse_linked_tool_mention(text, index, sigil)
            if parsed is not None:
                name, path, end_index = parsed
                if not _is_common_env_var(name):
                    if tool_kind_for_path(path) not in {
                        ToolMentionKind.APP,
                        ToolMentionKind.MCP,
                        ToolMentionKind.PLUGIN,
                    }:
                        mentioned_names.add(name)
                    mentioned_paths.add(path)
                index = end_index
                continue

        if character != sigil:
            index += 1
            continue

        name_start = index + 1
        if name_start >= len(text) or not _is_mention_name_char(text[name_start]):
            index += 1
            continue

        name_end = name_start + 1
        while name_end < len(text) and _is_mention_name_char(text[name_end]):
            name_end += 1

        name = text[name_start:name_end]
        if not _is_common_env_var(name):
            mentioned_names.add(name)
            plain_names.add(name)
        index = name_end

    return ToolMentions(
        names=frozenset(mentioned_names),
        paths=frozenset(mentioned_paths),
        plain_names=frozenset(plain_names),
    )


def collect_tool_mentions_from_messages(messages: Iterable[str]) -> CollectedToolMentions:
    return collect_tool_mentions_from_messages_with_sigil(messages, TOOL_MENTION_SIGIL)


def collect_tool_mentions_from_messages_with_sigil(
    messages: Iterable[str],
    sigil: str,
) -> CollectedToolMentions:
    _ensure_str(sigil, "sigil")
    if isinstance(messages, (str, bytes)):
        raise TypeError("messages must be an iterable of strings")
    plain_names: set[str] = set()
    paths: set[str] = set()
    for message in messages:
        _ensure_str(message, "message")
        mentions = extract_tool_mentions_with_sigil(message, sigil)
        plain_names.update(mentions.plain_names)
        paths.update(mentions.paths)
    return CollectedToolMentions(frozenset(plain_names), frozenset(paths))


def collect_explicit_app_ids(user_input: Iterable[Any]) -> set[str]:
    if isinstance(user_input, (str, bytes)):
        raise TypeError("user_input must be an iterable of user input items")
    items = tuple(user_input)
    messages = _text_messages(items)
    paths = set(_mention_paths(items))
    paths.update(collect_tool_mentions_from_messages(messages).paths)
    return {
        app_id
        for path in paths
        if tool_kind_for_path(path) is ToolMentionKind.APP
        for app_id in (app_id_from_path(path),)
        if app_id is not None
    }


def collect_explicit_plugin_mentions(
    user_input: Iterable[Any],
    plugins: Iterable[PluginCapabilitySummary | Mapping[str, JsonValue] | Any],
) -> list[PluginCapabilitySummary]:
    if isinstance(user_input, (str, bytes)):
        raise TypeError("user_input must be an iterable of user input items")
    if isinstance(plugins, (str, bytes)):
        raise TypeError("plugins must be an iterable of plugin summaries")
    plugin_items = tuple(PluginCapabilitySummary.from_value(plugin) for plugin in plugins)
    if not plugin_items:
        return []

    items = tuple(user_input)
    messages = _text_messages(items)
    paths = set(_mention_paths(items))
    paths.update(collect_tool_mentions_from_messages_with_sigil(messages, PLUGIN_TEXT_MENTION_SIGIL).paths)

    mentioned_config_names = {
        config_name
        for path in paths
        if tool_kind_for_path(path) is ToolMentionKind.PLUGIN
        for config_name in (plugin_config_name_from_path(path),)
        if config_name is not None
    }
    if not mentioned_config_names:
        return []

    return [plugin for plugin in plugin_items if plugin.config_name in mentioned_config_names]


def build_connector_slug_counts(connectors: Iterable[AppInfo | Mapping[str, JsonValue] | Any]) -> dict[str, int]:
    if isinstance(connectors, (str, bytes)):
        raise TypeError("connectors must be an iterable of connector infos")
    counts: Counter[str] = Counter()
    for connector in connectors:
        name = _connector_name(connector)
        counts[connector_name_slug(name)] += 1
    return dict(counts)


def _parse_linked_tool_mention(text: str, start: int, sigil: str) -> tuple[str, str, int] | None:
    _ensure_str(text, "text")
    if isinstance(start, bool) or not isinstance(start, int):
        raise TypeError("start must be an integer")
    if start < 0:
        raise ValueError("start must be non-negative")
    _ensure_str(sigil, "sigil")
    sigil_index = start + 1
    if sigil_index >= len(text) or text[sigil_index] != sigil:
        return None

    name_start = sigil_index + 1
    if name_start >= len(text) or not _is_mention_name_char(text[name_start]):
        return None

    name_end = name_start + 1
    while name_end < len(text) and _is_mention_name_char(text[name_end]):
        name_end += 1

    if name_end >= len(text) or text[name_end] != "]":
        return None

    path_start = name_end + 1
    while path_start < len(text) and _is_ascii_whitespace(text[path_start]):
        path_start += 1
    if path_start >= len(text) or text[path_start] != "(":
        return None

    path_end = path_start + 1
    while path_end < len(text) and text[path_end] != ")":
        path_end += 1
    if path_end >= len(text) or text[path_end] != ")":
        return None

    path = text[path_start + 1 : path_end].strip()
    if not path:
        return None
    return text[name_start:name_end], path, path_end + 1


def _is_mention_name_char(character: str) -> bool:
    _ensure_str(character, "character")
    if len(character) != 1:
        raise ValueError("character must be a single character")
    return character.isascii() and (character.isalnum() or character in "_-:")


def _is_ascii_whitespace(character: str) -> bool:
    _ensure_str(character, "character")
    if len(character) != 1:
        raise ValueError("character must be a single character")
    return character.isascii() and character.isspace()


def _is_common_env_var(name: str) -> bool:
    _ensure_str(name, "name")
    return name.upper() in _COMMON_ENV_VARS


def _text_messages(items: Iterable[Any]) -> list[str]:
    messages: list[str] = []
    for item in items:
        if _field_value(item, "type") != "text":
            continue
        text = _field_value(item, "text")
        if text is None:
            continue
        _ensure_str(text, "text")
        messages.append(text)
    return messages


def _mention_paths(items: Iterable[Any]) -> list[str]:
    paths: list[str] = []
    for item in items:
        if _field_value(item, "type") != "mention":
            continue
        path = _field_value(item, "path")
        if path is None:
            continue
        _ensure_str(path, "path")
        paths.append(path)
    return paths


def _connector_name(value: AppInfo | Mapping[str, JsonValue] | Any) -> str:
    if isinstance(value, AppInfo):
        return value.name
    if isinstance(value, Mapping):
        raw = value.get("name", value.get("display_name", value.get("id", "")))
        _ensure_str(raw, "connector name")
        return raw
    raw = getattr(value, "name", getattr(value, "display_name", getattr(value, "id", "")))
    _ensure_str(raw, "connector name")
    return raw


def _field_value(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _ensure_str(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")


def _ensure_str_frozenset(value: object, name: str) -> frozenset[str]:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        items = frozenset(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(f"{name} must be an iterable of strings") from exc
    if not all(isinstance(item, str) for item in items):
        raise TypeError(f"{name} must contain only strings")
    return items


__all__ = [
    "APP_PATH_PREFIX",
    "MCP_PATH_PREFIX",
    "PLUGIN_PATH_PREFIX",
    "SKILL_FILENAME",
    "SKILL_PATH_PREFIX",
    "CollectedToolMentions",
    "ToolMentionKind",
    "ToolMentions",
    "app_id_from_path",
    "build_connector_slug_counts",
    "collect_explicit_app_ids",
    "collect_explicit_plugin_mentions",
    "collect_tool_mentions_from_messages",
    "collect_tool_mentions_from_messages_with_sigil",
    "extract_tool_mentions",
    "extract_tool_mentions_with_sigil",
    "is_skill_filename",
    "normalize_skill_path",
    "plugin_config_name_from_path",
    "tool_kind_for_path",
]
