"""Serde adaptations owned by ``protocol/serde_helpers.rs``."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")
U = TypeVar("U")
MISSING = object()


def deserialize_empty_path_as_none(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return None if str(path) == "" or str(value) == "" else path


def deserialize_double_option(
    source: Mapping[str, Any],
    key: str,
    decoder: Callable[[Any], T] | None = None,
) -> T | None | object:
    if key not in source:
        return MISSING
    value = source[key]
    if value is None:
        return None
    return value if decoder is None else decoder(value)


def serialize_double_option(
    value: T | None | object,
    encoder: Callable[[T], U] | None = None,
) -> U | T | None | object:
    if value is MISSING or value is None:
        return value
    return value if encoder is None else encoder(value)


__all__ = [
    "MISSING",
    "deserialize_double_option",
    "deserialize_empty_path_as_none",
    "serialize_double_option",
]

