"""TOML-like config merge helpers ported from ``codex-config::merge``."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, Mapping

from .key_aliases import normalize_key_aliases, normalized_with_key_aliases
from pycodex.network_proxy import normalize_host


JsonValue = Any


def merge_toml_values(base: JsonValue, overlay: JsonValue) -> JsonValue:
    """Merge ``overlay`` into ``base``, giving ``overlay`` precedence.

    Mutable mapping inputs are updated in place and also returned, mirroring the
    Rust helper's ``&mut`` base argument.
    """

    return _merge_toml_values_at_path(base, overlay, ())


def _merge_toml_values_at_path(
    base: JsonValue, overlay: JsonValue, path: tuple[str, ...]
) -> JsonValue:
    if isinstance(base, MutableMapping) and isinstance(overlay, Mapping):
        normalize_key_aliases(path, base)
        overlay_table = dict(overlay)
        normalize_key_aliases(path, overlay_table)
        if _is_permission_network_domains_path(path):
            _normalize_network_domain_keys(base)
            _normalize_network_domain_keys(overlay_table)
        for key, value in overlay_table.items():
            if not isinstance(key, str):
                raise TypeError("config table keys must be strings")
            child_path = (*path, key)
            if key in base:
                base[key] = _merge_toml_values_at_path(base[key], value, child_path)
            else:
                base[key] = normalized_with_key_aliases(value, child_path)
        return base
    return normalized_with_key_aliases(overlay, path)


def _is_permission_network_domains_path(path: tuple[str, ...]) -> bool:
    return (
        len(path) == 4
        and path[0] == "permissions"
        and path[2] == "network"
        and path[3] == "domains"
    )


def _normalize_network_domain_keys(table: MutableMapping[str, JsonValue]) -> None:
    entries = list(table.items())
    table.clear()
    for pattern, value in entries:
        if not isinstance(pattern, str):
            raise TypeError("network domain patterns must be strings")
        table[normalize_host(pattern)] = value


__all__ = [
    "merge_toml_values",
    "normalize_key_aliases",
    "normalized_with_key_aliases",
]
