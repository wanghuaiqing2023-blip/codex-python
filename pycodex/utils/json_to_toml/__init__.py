"""JSON-to-TOML value conversion helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

TomlValue = Any


def json_to_toml(value: Any) -> TomlValue:
    """Convert a JSON-like Python value into a TOML-compatible value.

    Mirrors Rust ``codex-utils-json-to-toml``:
    ``null``/``None`` becomes an empty string, booleans remain booleans,
    integers/floats remain numeric values, arrays and objects recurse.
    """

    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {str(key): json_to_toml(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [json_to_toml(child) for child in value]
    return str(value)


__all__ = ["TomlValue", "json_to_toml"]
