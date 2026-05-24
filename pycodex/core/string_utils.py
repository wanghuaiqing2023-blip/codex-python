"""String helpers ported from ``codex/codex-rs/utils/string``."""

from __future__ import annotations

import json
import re
from typing import Any

APPROX_BYTES_PER_TOKEN = 4
UUID_RE = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
)


def take_bytes_at_char_boundary(value: str, max_bytes: int) -> str:
    text = str(value)
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def truncate_middle_chars(value: str, max_bytes: int) -> str:
    return _truncate_with_byte_estimate(str(value), max_bytes, use_tokens=False)


def truncate_middle_with_token_budget(value: str, max_tokens: int) -> tuple[str, int | None]:
    text = str(value)
    if not text:
        return "", None

    if max_tokens > 0 and len(text.encode("utf-8")) <= approx_bytes_for_tokens(max_tokens):
        return text, None

    truncated = _truncate_with_byte_estimate(
        text,
        approx_bytes_for_tokens(max_tokens),
        use_tokens=True,
    )
    total_tokens = approx_token_count(text)
    return (truncated, None) if truncated == text else (truncated, total_tokens)


def approx_token_count(text: str) -> int:
    byte_len = len(str(text).encode("utf-8"))
    return (byte_len + APPROX_BYTES_PER_TOKEN - 1) // APPROX_BYTES_PER_TOKEN


def approx_bytes_for_tokens(tokens: int) -> int:
    return max(tokens, 0) * APPROX_BYTES_PER_TOKEN


def approx_tokens_from_byte_count(bytes_count: int) -> int:
    bytes_count = max(bytes_count, 0)
    return (bytes_count + APPROX_BYTES_PER_TOKEN - 1) // APPROX_BYTES_PER_TOKEN


def sanitize_metric_tag_value(value: str) -> str:
    sanitized = "".join(
        ch if ch.isascii() and (ch.isalnum() or ch in "._-/") else "_"
        for ch in str(value)
    )
    trimmed = sanitized.strip("_")
    if not trimmed or all(not ch.isalnum() for ch in trimmed):
        return "unspecified"
    return trimmed[:256]


def find_uuids(value: str) -> list[str]:
    return UUID_RE.findall(str(value))


def normalize_markdown_hash_location_suffix(suffix: str) -> str | None:
    text = str(suffix)
    if not text.startswith("#"):
        return None
    fragment = text[1:]
    if "-" in fragment:
        start, end = fragment.split("-", 1)
    else:
        start, end = fragment, None

    start_point = _parse_markdown_hash_location_point(start)
    if start_point is None:
        return None
    start_line, start_column = start_point

    normalized = f":{start_line}"
    if start_column is not None:
        normalized += f":{start_column}"

    if end is not None:
        end_point = _parse_markdown_hash_location_point(end)
        if end_point is None:
            return None
        end_line, end_column = end_point
        normalized += f"-{end_line}"
        if end_column is not None:
            normalized += f":{end_column}"

    return normalized


def truncate_to_char_boundary(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    return str(value)[:max_chars]


def to_ascii_json_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _parse_markdown_hash_location_point(point: str) -> tuple[str, str | None] | None:
    if not point.startswith("L"):
        return None
    point = point[1:]
    if "C" in point:
        line, column = point.split("C", 1)
        return line, column
    return point, None


def _truncate_with_byte_estimate(text: str, max_bytes: int, use_tokens: bool) -> str:
    if not text:
        return ""

    byte_len = len(text.encode("utf-8"))
    total_chars = len(text)
    max_bytes = max(max_bytes, 0)
    if max_bytes == 0:
        return _format_truncation_marker(
            use_tokens,
            _removed_units(use_tokens, byte_len, total_chars),
        )

    if byte_len <= max_bytes:
        return text

    left_budget, right_budget = _split_budget(max_bytes)
    removed_chars, left, right = _split_string(text, left_budget, right_budget)
    marker = _format_truncation_marker(
        use_tokens,
        _removed_units(use_tokens, max(byte_len - max_bytes, 0), removed_chars),
    )
    return f"{left}{marker}{right}"


def _split_string(
    text: str,
    beginning_bytes: int,
    end_bytes: int,
) -> tuple[int, str, str]:
    if not text:
        return 0, "", ""

    encoded_len = len(text.encode("utf-8"))
    tail_start_target = max(encoded_len - max(end_bytes, 0), 0)
    prefix_end = 0
    suffix_start = len(text)
    removed_chars = 0
    suffix_started = False
    byte_index = 0

    for index, char in enumerate(text):
        char_end = byte_index + len(char.encode("utf-8"))
        if char_end <= beginning_bytes:
            prefix_end = index + 1
            byte_index = char_end
            continue

        if byte_index >= tail_start_target:
            if not suffix_started:
                suffix_start = index
                suffix_started = True
            byte_index = char_end
            continue

        removed_chars += 1
        byte_index = char_end

    if suffix_start < prefix_end:
        suffix_start = prefix_end

    return removed_chars, text[:prefix_end], text[suffix_start:]


def _split_budget(budget: int) -> tuple[int, int]:
    budget = max(budget, 0)
    left = budget // 2
    return left, budget - left


def _format_truncation_marker(use_tokens: bool, removed_count: int) -> str:
    unit = "tokens" if use_tokens else "chars"
    return f"\u2026{removed_count} {unit} truncated\u2026"


def _removed_units(use_tokens: bool, removed_bytes: int, removed_chars: int) -> int:
    if use_tokens:
        return approx_tokens_from_byte_count(removed_bytes)
    return max(removed_chars, 0)


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
    "truncate_to_char_boundary",
]
