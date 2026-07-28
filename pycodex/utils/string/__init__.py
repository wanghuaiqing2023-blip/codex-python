"""String helpers ported from ``codex-utils-string::lib``."""

from __future__ import annotations

import re
from typing import Any

from .json import to_ascii_json_string
from .truncate import (
    approx_bytes_for_tokens,
    approx_token_count,
    approx_tokens_from_byte_count,
    truncate_middle_chars,
    truncate_middle_with_token_budget,
)

UUID_RE = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
)


def take_bytes_at_char_boundary(value: str, max_bytes: int) -> str:
    text = _ensure_str(value, "value")
    max_bytes = _ensure_usize(max_bytes, "max_bytes")
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def sanitize_metric_tag_value(value: str) -> str:
    value = _ensure_str(value, "value")
    sanitized = "".join(
        ch if ch.isascii() and (ch.isalnum() or ch in "._-/") else "_"
        for ch in value
    )
    trimmed = sanitized.strip("_")
    if not trimmed or all(not ch.isascii() or not ch.isalnum() for ch in trimmed):
        return "unspecified"
    return trimmed[:256]


def find_uuids(value: str) -> list[str]:
    return UUID_RE.findall(_ensure_str(value, "value"))


def normalize_markdown_hash_location_suffix(suffix: str) -> str | None:
    text = _ensure_str(suffix, "suffix")
    if not text.startswith("#"):
        return None
    fragment = text[1:]
    start, separator, end = fragment.partition("-")
    start_point = _parse_markdown_hash_location_point(start)
    if start_point is None:
        return None
    start_line, start_column = start_point
    normalized = f":{start_line}"
    if start_column is not None:
        normalized += f":{start_column}"
    if separator:
        end_point = _parse_markdown_hash_location_point(end)
        if end_point is None:
            return None
        end_line, end_column = end_point
        normalized += f"-{end_line}"
        if end_column is not None:
            normalized += f":{end_column}"
    return normalized


def _parse_markdown_hash_location_point(point: str) -> tuple[str, str | None] | None:
    if not point.startswith("L"):
        return None
    point = point[1:]
    if "C" in point:
        line, column = point.split("C", 1)
        return line, column
    return point, None


def _ensure_str(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _ensure_usize(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


__all__ = [
    "approx_bytes_for_tokens",
    "approx_token_count",
    "approx_tokens_from_byte_count",
    "find_uuids",
    "normalize_markdown_hash_location_suffix",
    "sanitize_metric_tag_value",
    "take_bytes_at_char_boundary",
    "to_ascii_json_string",
    "truncate_middle_chars",
    "truncate_middle_with_token_budget",
]
