"""Config layer fingerprint helpers ported from ``codex-config``."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any


def record_origins(
    value: Any,
    meta: Any,
    path: list[str] | None = None,
    origins: MutableMapping[str, Any] | None = None,
) -> MutableMapping[str, Any]:
    """Record metadata for scalar TOML leaves using dotted paths."""

    path = [] if path is None else path
    origins = {} if origins is None else origins
    if isinstance(value, Mapping):
        for key, item in value.items():
            path.append(str(key))
            record_origins(item, meta, path, origins)
            path.pop()
        return origins
    if _is_array(value):
        for index, item in enumerate(value):
            path.append(str(index))
            record_origins(item, meta, path, origins)
            path.pop()
        return origins
    if path:
        origins[".".join(path)] = meta
    return origins


def version_for_toml(value: Any) -> str:
    """Return Rust's ``sha256:...`` config version for a TOML-like value."""

    canonical = _canonical_json(_to_json_value(value))
    serialized = json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(serialized).hexdigest()}"


def _canonical_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _canonical_json(value[key]) for key in sorted(value)}
    if _is_array(value):
        return [_canonical_json(item) for item in value]
    return value


def _to_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if _is_array(value):
        return [_to_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _is_array(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


__all__ = [
    "record_origins",
    "version_for_toml",
]
