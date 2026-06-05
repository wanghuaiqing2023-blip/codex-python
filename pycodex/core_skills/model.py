"""Core skill data model aligned with ``codex-rs/core-skills/src/model.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillToolDependency:
    type: str
    value: str
    description: str | None = None
    transport: str | None = None
    command: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class SkillDependencies:
    tools: tuple[SkillToolDependency, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "tools", tuple(self.tools))


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str = ""
    short_description: str | None = None
    interface: object | None = None
    dependencies: SkillDependencies | None = None
    policy: object | None = None
    path_to_skills_md: Path | str | None = None
    scope: str = "user"
    plugin_id: str | None = None


__all__ = [
    "SkillDependencies",
    "SkillMetadata",
    "SkillToolDependency",
]
