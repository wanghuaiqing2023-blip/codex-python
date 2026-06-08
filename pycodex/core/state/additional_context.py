"""Additional-context state ported from Codex core.

Rust source: codex/codex-rs/core/src/state/additional_context.rs
"""

from __future__ import annotations

from typing import Any, Mapping

from pycodex.core.context import (
    AdditionalContextDeveloperFragment,
    AdditionalContextUserFragment,
)
from pycodex.protocol import AdditionalContextEntry, AdditionalContextKind, ResponseInputItem


class AdditionalContextStore:
    def __init__(
        self,
        values: Mapping[str, AdditionalContextEntry | Mapping[str, Any] | Any] | None = None,
    ) -> None:
        self.values: dict[str, AdditionalContextEntry] = _normalize_values(values or {})

    def merge(
        self,
        values: Mapping[str, AdditionalContextEntry | Mapping[str, Any] | Any],
    ) -> tuple[ResponseInputItem, ...]:
        normalized = _normalize_values(values)
        fragments: list[ResponseInputItem] = []
        for key in sorted(normalized):
            entry = normalized[key]
            if self.values.get(key) == entry:
                continue
            if entry.kind is AdditionalContextKind.UNTRUSTED:
                fragments.append(
                    AdditionalContextUserFragment.new(key, entry.value).into_response_input_item()
                )
            elif entry.kind is AdditionalContextKind.APPLICATION:
                fragments.append(
                    AdditionalContextDeveloperFragment.new(key, entry.value).into_response_input_item()
                )
            else:
                raise ValueError(f"unknown additional context kind: {entry.kind}")
        self.values = normalized
        return tuple(fragments)


def _normalize_values(
    values: Mapping[str, AdditionalContextEntry | Mapping[str, Any] | Any],
) -> dict[str, AdditionalContextEntry]:
    if not isinstance(values, Mapping):
        raise TypeError("values must be a mapping")
    normalized: dict[str, AdditionalContextEntry] = {}
    for key, value in values.items():
        normalized[_ensure_str(key, "key")] = AdditionalContextEntry.from_value(value)
    return normalized


def _ensure_str(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


__all__ = [
    "AdditionalContextEntry",
    "AdditionalContextKind",
    "AdditionalContextStore",
]
