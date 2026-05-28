"""Config override parsing.

Ported from ``codex/codex-rs/utils/cli/src/config_override.rs``.

The upstream Rust code stores each ``-c key=value`` argument as raw text, then
parses it later into ``(path, toml::Value)`` pairs. This module keeps that
two-stage behavior while using only Python's standard library.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass, field
from typing import Any

from pycodex import _toml


UPSTREAM_CONFIG_OVERRIDE = "codex/codex-rs/utils/cli/src/config_override.rs"


class ConfigOverrideError(ValueError):
    """Raised when a raw config override cannot be split into a key/value pair."""


@dataclass(frozen=True)
class ConfigOverride:
    """Parsed config override pair."""

    path: str
    value: Any
    upstream_source: str = UPSTREAM_CONFIG_OVERRIDE


@dataclass
class CliConfigOverrides:
    """Raw ``-c key=value`` overrides captured from the CLI."""

    raw_overrides: list[str] = field(default_factory=list)

    def prepend_root_overrides(self, root_overrides: "CliConfigOverrides") -> None:
        """Prepend root-level overrides so later command-specific flags win."""

        self.raw_overrides[0:0] = root_overrides.raw_overrides

    def parse_overrides(self) -> list[ConfigOverride]:
        """Parse raw overrides into path/value pairs."""

        parsed: list[ConfigOverride] = []
        for raw in self.raw_overrides:
            parsed.append(parse_override(raw))
        return parsed

    def apply_on_mapping(self, target: MutableMapping[str, Any]) -> None:
        """Apply parsed overrides to a mutable mapping in place."""

        for override in self.parse_overrides():
            apply_single_override(target, override.path, override.value)


def parse_override(raw: str) -> ConfigOverride:
    """Parse one raw ``key=value`` override."""

    key, separator, value_raw = raw.partition("=")
    if not separator:
        raise ConfigOverrideError(f"Invalid override (missing '='): {raw}")

    key = key.strip()
    value_raw = value_raw.strip()

    if not key:
        raise ConfigOverrideError(f"Empty key in override: {raw}")

    try:
        value = parse_toml_value(value_raw)
    except ValueError:
        value = value_raw.strip().strip("\"'")

    return ConfigOverride(canonicalize_override_key(key), value)


def canonicalize_override_key(key: str) -> str:
    """Return the upstream canonical config path for legacy aliases."""

    if key == "use_legacy_landlock":
        return "features.use_legacy_landlock"
    return key


def parse_toml_value(raw: str) -> Any:
    """Parse a single TOML value using the upstream sentinel-key trick."""

    try:
        table = _toml.loads(f"_x_ = {raw}")
    except _toml.TOMLDecodeError as exc:
        raise ValueError(str(exc)) from exc

    try:
        return table["_x_"]
    except KeyError as exc:
        raise ValueError("missing sentinel key") from exc


def apply_single_override(target: MutableMapping[str, Any], path: str, value: Any) -> None:
    """Apply one parsed override to ``target`` in place."""

    parts = path.split(".")
    current: MutableMapping[str, Any] = target

    for index, part in enumerate(parts):
        is_last = index == len(parts) - 1
        if is_last:
            current[part] = value
            return

        next_value = current.get(part)
        if not isinstance(next_value, MutableMapping):
            next_value = {}
            current[part] = next_value
        current = next_value
