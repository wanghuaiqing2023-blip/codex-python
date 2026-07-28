"""UTF-8 middle truncation from ``codex-utils-string::truncate``."""

from __future__ import annotations

from typing import Any

APPROX_BYTES_PER_TOKEN = 4


def truncate_middle_chars(value: str, max_bytes: int) -> str:
    return _truncate_with_byte_estimate(
        _ensure_str(value, "value"),
        _ensure_usize(max_bytes, "max_bytes"),
        use_tokens=False,
    )


def truncate_middle_with_token_budget(
    value: str,
    max_tokens: int,
) -> tuple[str, int | None]:
    text = _ensure_str(value, "value")
    max_tokens = _ensure_usize(max_tokens, "max_tokens")
    if not text:
        return "", None
    if max_tokens > 0 and len(text.encode("utf-8")) <= approx_bytes_for_tokens(
        max_tokens
    ):
        return text, None
    truncated = _truncate_with_byte_estimate(
        text,
        approx_bytes_for_tokens(max_tokens),
        use_tokens=True,
    )
    total_tokens = approx_token_count(text)
    return (truncated, None) if truncated == text else (truncated, total_tokens)


def approx_token_count(text: str) -> int:
    byte_len = len(_ensure_str(text, "text").encode("utf-8"))
    return (byte_len + APPROX_BYTES_PER_TOKEN - 1) // APPROX_BYTES_PER_TOKEN


def approx_bytes_for_tokens(tokens: int) -> int:
    return _ensure_usize(tokens, "tokens") * APPROX_BYTES_PER_TOKEN


def approx_tokens_from_byte_count(bytes_count: int) -> int:
    bytes_count = _ensure_usize(bytes_count, "bytes_count")
    return (bytes_count + APPROX_BYTES_PER_TOKEN - 1) // APPROX_BYTES_PER_TOKEN


def _truncate_with_byte_estimate(
    text: str,
    max_bytes: int,
    use_tokens: bool,
) -> str:
    if not text:
        return ""
    byte_len = len(text.encode("utf-8"))
    total_chars = len(text)
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
        elif byte_index >= tail_start_target:
            if not suffix_started:
                suffix_start = index
                suffix_started = True
        else:
            removed_chars += 1
        byte_index = char_end
    if suffix_start < prefix_end:
        suffix_start = prefix_end
    return removed_chars, text[:prefix_end], text[suffix_start:]


def _split_budget(budget: int) -> tuple[int, int]:
    left = budget // 2
    return left, budget - left


def _format_truncation_marker(use_tokens: bool, removed_count: int) -> str:
    unit = "tokens" if use_tokens else "chars"
    return f"\u2026{removed_count} {unit} truncated\u2026"


def _removed_units(
    use_tokens: bool,
    removed_bytes: int,
    removed_chars: int,
) -> int:
    return (
        approx_tokens_from_byte_count(removed_bytes)
        if use_tokens
        else removed_chars
    )


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
    "truncate_middle_chars",
    "truncate_middle_with_token_budget",
]
