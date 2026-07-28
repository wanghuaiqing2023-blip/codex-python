"""CLI config overrides from Rust ``config_override.rs``."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CliConfigOverrides:
    raw_overrides: list[str] = field(default_factory=list)

    def prepend_root_overrides(self, root_overrides: "CliConfigOverrides") -> None:
        self.raw_overrides[0:0] = list(root_overrides.raw_overrides)

    def parse_overrides(self) -> list[tuple[str, Any]]:
        parsed: list[tuple[str, Any]] = []
        for raw in self.raw_overrides:
            key, separator, value_text = raw.partition("=")
            key = key.strip()
            if not separator:
                raise ValueError(f"Invalid override (missing '='): {raw}")
            if not key:
                raise ValueError(f"Empty key in override: {raw}")
            value_text = value_text.strip()
            try:
                value = tomllib.loads(f"_x_ = {value_text}")["_x_"]
            except Exception:
                value = value_text.strip().strip('"').strip("'")
            parsed.append((canonicalize_override_key(key), value))
        return parsed

    def apply_on_value(self, target: dict[str, Any]) -> None:
        if not isinstance(target, dict):
            raise TypeError("target must be a dict")
        for path, value in self.parse_overrides():
            apply_single_override(target, path, value)


def canonicalize_override_key(key: str) -> str:
    if key == "use_legacy_landlock":
        return "features.use_legacy_landlock"
    return key


def apply_single_override(root: dict[str, Any], path: str, value: Any) -> None:
    current: dict[str, Any] = root
    parts = path.split(".")
    for index, part in enumerate(parts):
        if index == len(parts) - 1:
            current[part] = value
            return
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child


__all__ = [
    "CliConfigOverrides",
    "apply_single_override",
    "canonicalize_override_key",
]
