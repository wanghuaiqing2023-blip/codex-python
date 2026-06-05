"""Skill enable/disable config rules ported from Codex core-skills.

This mirrors the dependency-free behavior in
``codex-rs/core-skills/src/config_rules.rs``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.core_skills.model import SkillMetadata
from pycodex.core_skills.invocation_utils import canonicalize_if_exists

JsonValue = Any


@dataclass(frozen=True)
class SkillConfigRuleSelector:
    type: str
    value: str | Path

    @classmethod
    def name(cls, name: str) -> "SkillConfigRuleSelector":
        return cls("name", name)

    @classmethod
    def path(cls, path: Path | str) -> "SkillConfigRuleSelector":
        return cls("path", canonicalize_if_exists(Path(path)))


@dataclass(frozen=True)
class SkillConfigRule:
    selector: SkillConfigRuleSelector
    enabled: bool


@dataclass(frozen=True)
class SkillConfigRules:
    entries: tuple[SkillConfigRule, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            object.__setattr__(self, "entries", tuple(self.entries))


def skill_config_rules_from_stack(config_layer_stack: Any) -> SkillConfigRules:
    entries: list[SkillConfigRule] = []
    for layer in _iter_layers(config_layer_stack):
        if not _is_user_or_session_layer(layer):
            continue
        config = _field_value(layer, "config", {})
        if not isinstance(config, Mapping):
            continue
        raw_skills = config.get("skills")
        for raw_entry in _iter_skill_config_entries(raw_skills):
            selector = skill_config_rule_selector(raw_entry)
            if selector is None:
                continue
            entries = [entry for entry in entries if entry.selector != selector]
            entries.append(SkillConfigRule(selector, _entry_enabled(raw_entry)))
    return SkillConfigRules(tuple(entries))


def resolve_disabled_skill_paths(
    skills: Iterable[SkillMetadata | Mapping[str, JsonValue] | Any],
    rules: SkillConfigRules | Iterable[SkillConfigRule],
) -> set[Path]:
    disabled_paths: set[Path] = set()
    skill_items = tuple(_coerce_skill_metadata(skill) for skill in skills)
    entries = rules.entries if isinstance(rules, SkillConfigRules) else tuple(rules)

    for entry in entries:
        selector = entry.selector
        if selector.type == "path":
            path = canonicalize_if_exists(Path(selector.value))
            if entry.enabled:
                disabled_paths.discard(path)
            else:
                disabled_paths.add(path)
            continue
        if selector.type == "name":
            name = str(selector.value)
            for skill in skill_items:
                if skill.name != name or skill.path_to_skills_md is None:
                    continue
                path = canonicalize_if_exists(Path(str(skill.path_to_skills_md)))
                if entry.enabled:
                    disabled_paths.discard(path)
                else:
                    disabled_paths.add(path)

    return disabled_paths


def skill_config_rule_selector(entry: Mapping[str, JsonValue] | Any) -> SkillConfigRuleSelector | None:
    path = _field_value(entry, "path")
    name = _field_value(entry, "name")
    has_path = path is not None
    has_name = name is not None
    if has_path and not has_name:
        return SkillConfigRuleSelector.path(Path(str(path)))
    if has_name and not has_path:
        trimmed = str(name).strip()
        if not trimmed:
            return None
        return SkillConfigRuleSelector.name(trimmed)
    return None


def _iter_layers(config_layer_stack: Any) -> Iterable[Any]:
    get_layers = getattr(config_layer_stack, "get_layers", None)
    if callable(get_layers):
        for args in (
            ("lowest_precedence_first", True),
            (),
        ):
            try:
                return tuple(get_layers(*args))
            except TypeError:
                continue
    if isinstance(config_layer_stack, Mapping):
        raw_layers = config_layer_stack.get("layers", ())
    else:
        raw_layers = config_layer_stack
    if isinstance(raw_layers, Iterable) and not isinstance(raw_layers, str | bytes):
        return tuple(raw_layers)
    return ()


def _iter_skill_config_entries(raw_skills: JsonValue) -> Iterable[Any]:
    if raw_skills is None:
        return ()
    if isinstance(raw_skills, Mapping):
        raw_entries = raw_skills.get("config", ())
    else:
        raw_entries = raw_skills
    if isinstance(raw_entries, Iterable) and not isinstance(raw_entries, str | bytes):
        return tuple(raw_entries)
    return ()


def _is_user_or_session_layer(layer: Any) -> bool:
    name = _field_value(layer, "name", _field_value(layer, "source"))
    if isinstance(name, Mapping):
        if "User" in name or "user" in name:
            return True
        name = next(iter(name), "")
    normalized = str(name).replace("-", "_").lower()
    return normalized in {"user", "sessionflags", "session_flags"}


def _entry_enabled(entry: Mapping[str, JsonValue] | Any) -> bool:
    return bool(_field_value(entry, "enabled", True))


def _coerce_skill_metadata(value: SkillMetadata | Mapping[str, JsonValue] | Any) -> SkillMetadata:
    if isinstance(value, SkillMetadata):
        return value
    if isinstance(value, Mapping):
        path = value.get("path_to_skills_md", value.get("path"))
        return SkillMetadata(
            name=str(value["name"]),
            path_to_skills_md=None if path is None else Path(str(path)),
        )
    path = _field_value(value, "path_to_skills_md", _field_value(value, "path"))
    return SkillMetadata(
        name=str(_field_value(value, "name")),
        path_to_skills_md=None if path is None else Path(str(path)),
    )


def _field_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "SkillConfigRule",
    "SkillConfigRuleSelector",
    "SkillConfigRules",
    "resolve_disabled_skill_paths",
    "skill_config_rule_selector",
    "skill_config_rules_from_stack",
]
