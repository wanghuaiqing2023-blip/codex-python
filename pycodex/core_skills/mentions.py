"""Explicit skill mention selection ported from Codex core-skills.

This is the standard-library slice of
``codex-rs/core-skills/src/injection.rs`` and
``codex-rs/core-skills/src/mention_counts.rs``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pycodex.core_skills.model import SkillMetadata
from pycodex.core.plugins.mentions import (
    ToolMentionKind,
    extract_tool_mentions,
    normalize_skill_path,
    tool_kind_for_path,
)

JsonValue = Any


def build_skill_name_counts(
    skills: Iterable[SkillMetadata | Mapping[str, JsonValue] | Any],
    disabled_paths: Iterable[Path | str] = (),
) -> tuple[dict[str, int], dict[str, int]]:
    disabled = {_path_key(path) for path in disabled_paths}
    exact_counts: Counter[str] = Counter()
    lower_counts: Counter[str] = Counter()
    for skill in skills:
        metadata = _coerce_skill_metadata(skill)
        path = _skill_path_key(metadata)
        if path is not None and path in disabled:
            continue
        exact_counts[metadata.name] += 1
        lower_counts[metadata.name.lower()] += 1
    return dict(exact_counts), dict(lower_counts)


def text_mentions_skill(text: str, skill_name: str) -> bool:
    if not skill_name:
        return False
    mention = f"${skill_name}"
    start = 0
    while True:
        index = text.find(mention, start)
        if index < 0:
            return False
        after_index = index + len(mention)
        if after_index >= len(text) or not _is_mention_name_char(text[after_index]):
            return True
        start = index + 1


def collect_explicit_skill_mentions(
    inputs: Iterable[Any],
    skills: Iterable[SkillMetadata | Mapping[str, JsonValue] | Any],
    disabled_paths: Iterable[Path | str] = (),
    connector_slug_counts: Mapping[str, int] | None = None,
) -> list[SkillMetadata]:
    skill_items = tuple(_coerce_skill_metadata(skill) for skill in skills)
    disabled = {_path_key(path) for path in disabled_paths}
    exact_counts, _lower_counts = build_skill_name_counts(skill_items, disabled)
    connector_counts = connector_slug_counts or {}

    selected: list[SkillMetadata] = []
    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    blocked_plain_names: set[str] = set()
    input_items = tuple(inputs)

    for item in input_items:
        if _field_value(item, "type") != "skill":
            continue
        name = _field_value(item, "name")
        if name is not None:
            blocked_plain_names.add(str(name))
        path = _field_value(item, "path")
        if path is None:
            continue
        path_key = _path_key(path)
        if path_key in disabled or path_key in seen_paths:
            continue
        skill = next((candidate for candidate in skill_items if _skill_path_key(candidate) == path_key), None)
        if skill is None:
            continue
        seen_paths.add(path_key)
        seen_names.add(skill.name)
        selected.append(skill)

    for item in input_items:
        if _field_value(item, "type") != "text":
            continue
        text = _field_value(item, "text")
        if text is None:
            continue
        _select_skills_from_mentions(
            str(text),
            skill_items,
            disabled,
            exact_counts,
            connector_counts,
            blocked_plain_names,
            seen_names,
            seen_paths,
            selected,
        )

    return selected


def _select_skills_from_mentions(
    text: str,
    skills: tuple[SkillMetadata, ...],
    disabled_paths: set[str],
    skill_name_counts: Mapping[str, int],
    connector_slug_counts: Mapping[str, int],
    blocked_plain_names: set[str],
    seen_names: set[str],
    seen_paths: set[str],
    selected: list[SkillMetadata],
) -> None:
    mentions = extract_tool_mentions(text)
    if mentions.is_empty():
        return

    mentioned_skill_paths = {
        _path_key(normalize_skill_path(path))
        for path in mentions.paths
        if tool_kind_for_path(path)
        not in {
            ToolMentionKind.APP,
            ToolMentionKind.MCP,
            ToolMentionKind.PLUGIN,
        }
    }

    for skill in skills:
        path = _skill_path_key(skill)
        if path is None or path in disabled_paths or path in seen_paths:
            continue
        if path not in mentioned_skill_paths:
            continue
        seen_paths.add(path)
        seen_names.add(skill.name)
        selected.append(skill)

    for skill in skills:
        path = _skill_path_key(skill)
        if path is None or path in disabled_paths or path in seen_paths:
            continue
        if skill.name in blocked_plain_names or skill.name not in mentions.plain_names:
            continue
        if skill_name_counts.get(skill.name, 0) != 1:
            continue
        if connector_slug_counts.get(skill.name.lower(), 0) != 0:
            continue
        if skill.name in seen_names:
            continue
        seen_names.add(skill.name)
        seen_paths.add(path)
        selected.append(skill)


def _coerce_skill_metadata(value: SkillMetadata | Mapping[str, JsonValue] | Any) -> SkillMetadata:
    if isinstance(value, SkillMetadata):
        return value
    if isinstance(value, Mapping):
        path = value.get("path_to_skills_md", value.get("path"))
        return SkillMetadata(
            name=str(value["name"]),
            dependencies=value.get("dependencies"),
            description=str(value.get("description", "")),
            short_description=_optional_str(value.get("short_description", value.get("shortDescription"))),
            interface=value.get("interface"),
            policy=value.get("policy"),
            path_to_skills_md=None if path is None else Path(str(path)),
            scope=str(value.get("scope", "user")),
            plugin_id=_optional_str(value.get("plugin_id", value.get("pluginId"))),
        )
    path = _field_value(value, "path_to_skills_md", _field_value(value, "path"))
    return SkillMetadata(
        name=str(_field_value(value, "name")),
        dependencies=_field_value(value, "dependencies"),
        description=str(_field_value(value, "description", "")),
        short_description=_optional_str(_field_value(value, "short_description")),
        interface=_field_value(value, "interface"),
        policy=_field_value(value, "policy"),
        path_to_skills_md=None if path is None else Path(str(path)),
        scope=str(_field_value(value, "scope", "user")),
        plugin_id=_optional_str(_field_value(value, "plugin_id")),
    )


def _skill_path_key(skill: SkillMetadata) -> str | None:
    if skill.path_to_skills_md is None:
        return None
    return _path_key(skill.path_to_skills_md)


def _path_key(path: Path | str) -> str:
    return str(path).replace("\\", "/").rstrip("/") or "/"


def _is_mention_name_char(character: str) -> bool:
    return character.isascii() and (character.isalnum() or character in "_-:")


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _field_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "build_skill_name_counts",
    "collect_explicit_skill_mentions",
    "text_mentions_skill",
]
