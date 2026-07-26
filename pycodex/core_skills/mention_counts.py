"""Skill-name counting ported from ``codex-core-skills::mention_counts``."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .model import SkillMetadata


def build_skill_name_counts(
    skills: Iterable[SkillMetadata | Mapping[str, Any] | Any],
    disabled_paths: Iterable[Path | str] = (),
) -> tuple[dict[str, int], dict[str, int]]:
    disabled = {_path_key(path) for path in disabled_paths}
    exact_counts: Counter[str] = Counter()
    lower_counts: Counter[str] = Counter()
    for skill in skills:
        name = str(_field_value(skill, "name"))
        path = _field_value(skill, "path_to_skills_md", _field_value(skill, "path"))
        if path is not None and _path_key(path) in disabled:
            continue
        exact_counts[name] += 1
        lower_counts[name.lower()] += 1
    return dict(exact_counts), dict(lower_counts)


def _field_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _path_key(path: Path | str) -> str:
    return str(path).replace("\\", "/").rstrip("/") or "/"


__all__ = ["build_skill_name_counts"]
