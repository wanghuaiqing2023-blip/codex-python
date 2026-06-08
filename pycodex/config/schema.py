"""Config schema helpers ported from ``codex-config::schema``."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

JsonValue = Any


def canonicalize(value: JsonValue) -> JsonValue:
    """Return a JSON-compatible value with object keys sorted recursively."""

    if isinstance(value, Mapping):
        return {str(key): canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    if isinstance(value, tuple):
        return [canonicalize(item) for item in value]
    return value


def config_schema() -> dict[str, JsonValue]:
    """Return the checked-in config schema fixture as a JSON object."""

    fixture = _config_schema_fixture_path()
    value = json.loads(fixture.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("config schema fixture must be a JSON object")
    return value


def config_schema_json() -> bytes:
    """Render the config schema as canonical pretty-printed JSON bytes."""

    value = canonicalize(config_schema())
    return json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")


def write_config_schema(out_path: str | Path) -> None:
    """Write the canonical config schema JSON to ``out_path``."""

    Path(out_path).write_bytes(config_schema_json())


def _config_schema_fixture_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "codex" / "codex-rs" / "core" / "config.schema.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("codex/codex-rs/core/config.schema.json")


__all__ = [
    "canonicalize",
    "config_schema",
    "config_schema_json",
    "write_config_schema",
]
