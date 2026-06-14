"""Skill metadata helpers for TUI skill pickers and search.

Rust counterpart: ``codex-rs/tui/src/skills_helpers.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .text_formatting import truncate_text

SKILL_NAME_TRUNCATE_LEN = 21


@dataclass(frozen=True)
class SkillInterfaceMetadata:
    display_name: str | None = None
    short_description: str | None = None


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    short_description: str | None = None
    interface: SkillInterfaceMetadata | Mapping[str, Any] | None = None


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def skill_display_name(skill: SkillMetadata | Mapping[str, Any] | Any) -> str:
    interface = _field(skill, "interface")
    display_name = _field(interface, "display_name") if interface is not None else None
    if display_name is not None:
        return str(display_name)

    name = str(_field(skill, "name", ""))
    plugin_name, sep, skill_name = name.partition(":")
    if sep and plugin_name and skill_name:
        return f"{skill_name} ({plugin_name})"
    return name


def skill_description(skill: SkillMetadata | Mapping[str, Any] | Any) -> str:
    interface = _field(skill, "interface")
    interface_short = _field(interface, "short_description") if interface is not None else None
    if interface_short is not None:
        return str(interface_short)

    short_description = _field(skill, "short_description")
    if short_description is not None:
        return str(short_description)

    return str(_field(skill, "description", ""))


def truncate_skill_name(name: str) -> str:
    return truncate_text(str(name), SKILL_NAME_TRUNCATE_LEN)


def _fuzzy_match(candidate: str, needle: str) -> tuple[list[int], int] | None:
    """Small stdlib fuzzy subsequence matcher.

    The Rust code delegates to ``codex_utils_fuzzy_match::fuzzy_match``. Python
    keeps the same boundary shape: matched character indices plus an integer score,
    with contiguous/case-exact matches scoring higher than sparse matches.
    """

    if needle == "":
        return ([], 0)

    candidate_lower = candidate.lower()
    needle_lower = needle.lower()
    indices: list[int] = []
    start = 0
    for char in needle_lower:
        found = candidate_lower.find(char, start)
        if found < 0:
            return None
        indices.append(found)
        start = found + 1

    contiguous_bonus = sum(1 for left, right in zip(indices, indices[1:]) if right == left + 1)
    exact_bonus = sum(1 for idx, char in zip(indices, needle) if candidate[idx : idx + 1] == char)
    compactness = indices[-1] - indices[0] + 1 if indices else 0
    score = len(indices) * 100 + contiguous_bonus * 20 + exact_bonus * 5 - compactness
    return (indices, score)


def match_skill(
    filter: str,
    display_name: str,
    skill_name: str,
) -> tuple[list[int] | None, int] | None:
    display_match = _fuzzy_match(str(display_name), str(filter))
    if display_match is not None:
        indices, score = display_match
        return (indices, score)

    if display_name != skill_name:
        skill_match = _fuzzy_match(str(skill_name), str(filter))
        if skill_match is not None:
            _indices, score = skill_match
            return (None, score)

    return None


__all__ = [
    "SKILL_NAME_TRUNCATE_LEN",
    "SkillInterfaceMetadata",
    "SkillMetadata",
    "match_skill",
    "skill_description",
    "skill_display_name",
    "truncate_skill_name",
]
