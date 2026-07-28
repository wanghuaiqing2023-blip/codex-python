"""Fuzzy line-sequence lookup owned by ``seek_sequence.rs``."""

from __future__ import annotations

def seek_sequence(
    lines: list[str],
    pattern: tuple[str, ...],
    start: int,
    *,
    eof: bool,
) -> int | None:
    if not pattern:
        return start
    if len(pattern) > len(lines):
        return None

    max_start = len(lines) - len(pattern)
    search_start = max_start if eof and len(lines) >= len(pattern) else start
    if search_start > max_start:
        return None

    for line_index in range(search_start, max_start + 1):
        if tuple(lines[line_index : line_index + len(pattern)]) == pattern:
            return line_index

    for line_index in range(search_start, max_start + 1):
        if all(
            lines[line_index + pattern_index].rstrip() == expected.rstrip()
            for pattern_index, expected in enumerate(pattern)
        ):
            return line_index

    for line_index in range(search_start, max_start + 1):
        if all(
            lines[line_index + pattern_index].strip() == expected.strip()
            for pattern_index, expected in enumerate(pattern)
        ):
            return line_index

    for line_index in range(search_start, max_start + 1):
        if all(
            _normalise_patch_seek_line(lines[line_index + pattern_index])
            == _normalise_patch_seek_line(expected)
            for pattern_index, expected in enumerate(pattern)
        ):
            return line_index

    return None

_PATCH_SEEK_NORMALISE_MAP = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u00a0": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u2007": " ",
        "\u2008": " ",
        "\u2009": " ",
        "\u200a": " ",
        "\u202f": " ",
        "\u205f": " ",
        "\u3000": " ",
    }
)

def _normalise_patch_seek_line(value: str) -> str:
    return value.strip().translate(_PATCH_SEEK_NORMALISE_MAP)

__all__ = ["seek_sequence"]
