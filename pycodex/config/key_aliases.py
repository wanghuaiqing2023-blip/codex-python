"""Config key alias normalization ported from ``codex-config``."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

JsonValue = Any


@dataclass(frozen=True)
class ConfigKeyAlias:
    table_path: tuple[str, ...]
    legacy_key: str
    canonical_key: str


CONFIG_KEY_ALIASES = (
    ConfigKeyAlias(
        table_path=("memories",),
        legacy_key="no_memories_if_mcp_or_web_search",
        canonical_key="disable_on_external_context",
    ),
)


def normalize_key_aliases(path: tuple[str, ...], table: MutableMapping[str, JsonValue]) -> None:
    for alias in CONFIG_KEY_ALIASES:
        if path == alias.table_path and alias.legacy_key in table:
            value = table.pop(alias.legacy_key)
            table.setdefault(alias.canonical_key, value)


def normalized_with_key_aliases(value: JsonValue, path: tuple[str, ...] = ()) -> JsonValue:
    if isinstance(value, Mapping):
        normalized: dict[str, JsonValue] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("config table keys must be strings")
            normalized[key] = normalized_with_key_aliases(child, (*path, key))
        normalize_key_aliases(path, normalized)
        return normalized
    if isinstance(value, list):
        return [normalized_with_key_aliases(item, path) for item in value]
    return value


__all__ = [
    "CONFIG_KEY_ALIASES",
    "ConfigKeyAlias",
    "normalize_key_aliases",
    "normalized_with_key_aliases",
]
