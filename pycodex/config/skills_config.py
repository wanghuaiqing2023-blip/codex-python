"""Skill-related config shapes ported from ``codex-config``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonValue = Any


@dataclass(frozen=True)
class SkillConfig:
    path: Path | None = None
    name: str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.path is not None:
            object.__setattr__(self, "path", Path(self.path))
        if self.name is not None and not isinstance(self.name, str):
            raise TypeError("name must be a string or None")
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a bool")

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "SkillConfig":
        _reject_unknown_fields(value, {"path", "name", "enabled"}, "SkillConfig")
        path = value.get("path")
        if path is not None and not isinstance(path, (str, Path)):
            raise TypeError("path must be a string path or None")
        name = value.get("name")
        if name is not None and not isinstance(name, str):
            raise TypeError("name must be a string or None")
        enabled = value.get("enabled", True)
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool")
        return cls(path=Path(path) if path is not None else None, name=name, enabled=enabled)

    def to_mapping(self) -> dict[str, JsonValue]:
        output: dict[str, JsonValue] = {"enabled": self.enabled}
        if self.path is not None:
            output["path"] = str(self.path)
        if self.name is not None:
            output["name"] = self.name
        return output


@dataclass(frozen=True)
class BundledSkillsConfig:
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a bool")

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "BundledSkillsConfig":
        if value is None:
            return cls()
        _reject_unknown_fields(value, {"enabled"}, "BundledSkillsConfig")
        enabled = value.get("enabled", True)
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool")
        return cls(enabled=enabled)

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"enabled": self.enabled}


@dataclass(frozen=True)
class SkillsConfig:
    bundled: BundledSkillsConfig | None = None
    include_instructions: bool | None = None
    config: tuple[SkillConfig, ...] = ()

    def __post_init__(self) -> None:
        if self.bundled is not None and not isinstance(self.bundled, BundledSkillsConfig):
            if isinstance(self.bundled, Mapping):
                object.__setattr__(self, "bundled", BundledSkillsConfig.from_mapping(self.bundled))
            else:
                raise TypeError("bundled must be BundledSkillsConfig, mapping, or None")
        if self.include_instructions is not None and not isinstance(self.include_instructions, bool):
            raise TypeError("include_instructions must be a bool or None")
        if isinstance(self.config, (str, bytes)) or not isinstance(self.config, Sequence):
            raise TypeError("config must be a sequence")
        object.__setattr__(
            self,
            "config",
            tuple(
                item if isinstance(item, SkillConfig) else SkillConfig.from_mapping(item)
                for item in self.config
            ),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "SkillsConfig":
        if value is None:
            return cls()
        _reject_unknown_fields(value, {"bundled", "include_instructions", "config"}, "SkillsConfig")
        bundled_value = value.get("bundled")
        if bundled_value is not None and not isinstance(bundled_value, Mapping):
            raise TypeError("bundled must be a table or None")
        include_instructions = value.get("include_instructions")
        if include_instructions is not None and not isinstance(include_instructions, bool):
            raise TypeError("include_instructions must be a bool or None")
        config_value = value.get("config", ())
        if isinstance(config_value, (str, bytes)) or not isinstance(config_value, Sequence):
            raise TypeError("config must be an array")
        return cls(
            bundled=BundledSkillsConfig.from_mapping(bundled_value) if bundled_value is not None else None,
            include_instructions=include_instructions,
            config=tuple(
                item if isinstance(item, SkillConfig) else SkillConfig.from_mapping(item)
                for item in config_value
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        output: dict[str, JsonValue] = {}
        if self.bundled is not None:
            output["bundled"] = self.bundled.to_mapping()
        if self.include_instructions is not None:
            output["include_instructions"] = self.include_instructions
        if self.config:
            output["config"] = [entry.to_mapping() for entry in self.config]
        return output


def _reject_unknown_fields(value: Mapping[str, JsonValue], allowed: set[str], type_name: str) -> None:
    unknown = [str(key) for key in value if key not in allowed]
    if unknown:
        raise ValueError(f"unknown fields for {type_name}: {', '.join(unknown)}")


__all__ = [
    "BundledSkillsConfig",
    "SkillConfig",
    "SkillsConfig",
]
