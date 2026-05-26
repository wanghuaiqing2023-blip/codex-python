"""Skill injection loading helpers ported from Codex core-skills.

This mirrors the dependency-free part of
``codex-rs/core-skills/src/injection.rs``: turning explicitly mentioned skill
metadata into ordered injection records and warnings.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.core.mcp_skill_dependencies import SkillMetadata

JsonValue = Any
SkillReadText = Callable[[Path], str]


@dataclass(frozen=True)
class SkillInjection:
    name: str
    path: str
    contents: str


@dataclass(frozen=True)
class SkillInjections:
    items: tuple[SkillInjection, ...] = ()
    warnings: tuple[str, ...] = ()


def build_skill_injections(
    mentioned_skills: Iterable[SkillMetadata | Mapping[str, JsonValue] | Any],
    read_text: SkillReadText | None = None,
) -> SkillInjections:
    skills = tuple(_coerce_skill_metadata(skill) for skill in mentioned_skills)
    if not skills:
        return SkillInjections()

    items: list[SkillInjection] = []
    warnings: list[str] = []
    reader = read_text or _default_read_text

    for skill in skills:
        path = _skill_path(skill)
        if path is None:
            warnings.append(f"Failed to load skill {skill.name} at : missing skill path")
            continue
        try:
            contents = reader(path)
        except Exception as err:
            warnings.append(f"Failed to load skill {skill.name} at {path}: {err}")
            continue
        items.append(SkillInjection(skill.name, str(path), contents))

    return SkillInjections(tuple(items), tuple(warnings))


def _default_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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


def _skill_path(skill: SkillMetadata) -> Path | None:
    if skill.path_to_skills_md is None:
        return None
    return Path(str(skill.path_to_skills_md))


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _field_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "SkillInjection",
    "SkillInjections",
    "SkillReadText",
    "build_skill_injections",
]
