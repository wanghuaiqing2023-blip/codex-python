"""Fuzzy subsequence matching ported from ``codex-utils-fuzzy-match``."""

from __future__ import annotations

I32_MAX = 2_147_483_647


def fuzzy_match(haystack: str, needle: str) -> tuple[list[int], int] | None:
    if not isinstance(haystack, str):
        raise TypeError("haystack must be a string")
    if not isinstance(needle, str):
        raise TypeError("needle must be a string")
    if needle == "":
        return ([], I32_MAX)

    lowered_chars: list[str] = []
    lowered_to_orig_char_idx: list[int] = []
    for orig_idx, ch in enumerate(haystack):
        for lowered in ch.lower():
            lowered_chars.append(lowered)
            lowered_to_orig_char_idx.append(orig_idx)

    lowered_needle = list(needle.lower())

    result_orig_indices: list[int] = []
    last_lower_pos: int | None = None
    cur = 0
    for needle_char in lowered_needle:
        found_at: int | None = None
        while cur < len(lowered_chars):
            if lowered_chars[cur] == needle_char:
                found_at = cur
                cur += 1
                break
            cur += 1
        if found_at is None:
            return None
        result_orig_indices.append(lowered_to_orig_char_idx[found_at])
        last_lower_pos = found_at

    if result_orig_indices:
        target_orig = result_orig_indices[0]
        first_lower_pos = next(
            (idx for idx, orig_idx in enumerate(lowered_to_orig_char_idx) if orig_idx == target_orig),
            0,
        )
    else:
        first_lower_pos = 0

    if last_lower_pos is None:
        last_lower_pos = first_lower_pos
    window = (last_lower_pos - first_lower_pos + 1) - len(lowered_needle)
    score = max(window, 0)
    if first_lower_pos == 0:
        score -= 100

    result_orig_indices = sorted(set(result_orig_indices))
    return (result_orig_indices, score)


__all__ = ["I32_MAX", "fuzzy_match"]
