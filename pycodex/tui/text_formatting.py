"""Text formatting helpers for TUI display.

Upstream source: ``codex/codex-rs/tui/src/text_formatting.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import unicodedata
from typing import Iterable, List, Optional, Tuple

from ._porting import RustTuiModule
from .line_truncation import _display_width

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="text_formatting",
    source="codex/codex-rs/tui/src/text_formatting.rs",
    status="complete",
)


ELLIPSIS = "…"


def capitalize_first(input: str) -> str:
    """Uppercase the first Unicode scalar and keep the rest unchanged."""

    if not input:
        return ""
    return input[0].upper() + input[1:]


def _graphemes(text: str) -> List[str]:
    """Small stdlib grapheme approximation for Rust unicode-segmentation usage."""

    clusters: List[str] = []
    for ch in text:
        if clusters and unicodedata.combining(ch):
            clusters[-1] += ch
        else:
            clusters.append(ch)
    return clusters


def truncate_text(text: str, max_graphemes: int) -> str:
    """Truncate text to at most ``max_graphemes`` grapheme clusters."""

    if max_graphemes < 0:
        raise ValueError("max_graphemes must be non-negative")
    graphemes = _graphemes(text)
    if len(graphemes) <= max_graphemes:
        return text
    if max_graphemes >= 3:
        return "".join(graphemes[: max_graphemes - 3]) + "..."
    return "".join(graphemes[:max_graphemes])


def _json_to_compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ": "))


def _space_after_commas(text: str) -> str:
    out: List[str] = []
    in_string = False
    escape_next = False
    for ch in text:
        out.append(ch)
        if ch == '"' and not escape_next:
            in_string = not in_string
        if ch == "\\" and in_string:
            escape_next = not escape_next
        else:
            if escape_next and in_string:
                escape_next = False
        if ch == "," and not in_string:
            out.append(" ")
    return "".join(out)


def format_json_compact(text: str) -> Optional[str]:
    """Format JSON as one compact line with spaces after commas/colons."""

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return _space_after_commas(_json_to_compact(parsed))


def format_and_truncate_tool_result(text: str, max_lines: int, line_width: int) -> str:
    """Compact JSON if possible, then truncate to the approximate display budget."""

    if max_lines < 0 or line_width < 0:
        raise ValueError("max_lines and line_width must be non-negative")
    max_graphemes = max(max_lines * line_width - max_lines, 0)
    formatted_json = format_json_compact(text)
    return truncate_text(formatted_json if formatted_json is not None else text, max_graphemes)


def _front_truncate(original: str, allowed_width: int) -> str:
    if allowed_width <= 0:
        return ""
    if _display_width(original) <= allowed_width:
        return original
    if allowed_width == 1:
        return ELLIPSIS
    kept: List[str] = []
    used_width = 1
    for ch in reversed(original):
        ch_width = _display_width(ch)
        if used_width + ch_width > allowed_width:
            break
        used_width += ch_width
        kept.append(ch)
    kept.reverse()
    return ELLIPSIS + "".join(kept)


@dataclass
class Segment:
    original: str
    text: str
    truncatable: bool
    is_suffix: bool


def center_truncate_path(path: str, max_width: int) -> str:
    """Center-truncate a path-like string to a display width."""

    if max_width < 0:
        raise ValueError("max_width must be non-negative")
    if max_width == 0:
        return ""
    if _display_width(path) <= max_width:
        return path

    sep = os.sep
    has_leading_sep = path.startswith(sep)
    has_trailing_sep = path.endswith(sep)
    raw_segments = path.split(sep)
    if has_leading_sep and raw_segments and raw_segments[0] == "":
        raw_segments.pop(0)
    if has_trailing_sep and raw_segments and raw_segments[-1] == "":
        raw_segments.pop()
    if not raw_segments:
        return sep if has_leading_sep and _display_width(sep) <= max_width else ELLIPSIS

    def assemble(leading: bool, segments: List[Segment]) -> str:
        result = sep if leading else ""
        for segment in segments:
            if result and not result.endswith(sep):
                result += sep
            result += segment.text
        return result

    segment_count = len(raw_segments)
    combos: List[Tuple[int, int]] = []
    for left in range(1, segment_count + 1):
        min_right = 0 if left == segment_count else 1
        for right in range(min_right, segment_count - left + 1):
            combos.append((left, right))

    desired_suffix = min(2, segment_count - 1) if segment_count > 1 else 0
    prioritized = [combo for combo in combos if combo[1] >= desired_suffix]
    fallback = [combo for combo in combos if combo[1] < desired_suffix]
    prioritized.sort(key=lambda item: (-item[0], -item[1], -(item[0] + item[1])))
    fallback.sort(key=lambda item: (-item[0], -item[1], -(item[0] + item[1])))

    def fit_segments(segments: List[Segment], allow_front_truncate: bool) -> Optional[str]:
        while True:
            candidate = assemble(has_leading_sep, segments)
            width = _display_width(candidate)
            if width <= max_width:
                return candidate
            if not allow_front_truncate:
                return None

            indices = [
                idx for idx in reversed(range(len(segments))) if segments[idx].truncatable and segments[idx].is_suffix
            ]
            indices.extend(
                idx for idx in reversed(range(len(segments))) if segments[idx].truncatable and not segments[idx].is_suffix
            )
            if not indices:
                return None

            changed = False
            for idx in indices:
                if _display_width(segments[idx].original) <= max_width and segment_count > 2:
                    continue
                seg_width = _display_width(segments[idx].text)
                other_width = max(width - seg_width, 0)
                allowed_width = max(max_width - other_width, 1)
                new_text = _front_truncate(segments[idx].original, allowed_width)
                if new_text != segments[idx].text:
                    segments[idx].text = new_text
                    changed = True
                    break
            if not changed:
                return None

    for left_count, right_count in [*prioritized, *fallback]:
        segments = [
            Segment(original=seg, text=seg, truncatable=True, is_suffix=False)
            for seg in raw_segments[:left_count]
        ]
        need_ellipsis = left_count + right_count < segment_count
        if need_ellipsis:
            segments.append(Segment(original=ELLIPSIS, text=ELLIPSIS, truncatable=False, is_suffix=False))
        if right_count > 0:
            segments.extend(
                Segment(original=seg, text=seg, truncatable=True, is_suffix=True)
                for seg in raw_segments[segment_count - right_count :]
            )
        allow_front_truncate = need_ellipsis or segment_count <= 2
        candidate = fit_segments(segments, allow_front_truncate)
        if candidate is not None:
            return candidate

    return _front_truncate(path, max_width)


def proper_join(items: Iterable[str]) -> str:
    values = [str(item) for item in items]
    if len(values) == 0:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])} and {values[-1]}"


__all__ = [
    "ELLIPSIS",
    "RUST_MODULE",
    "Segment",
    "capitalize_first",
    "center_truncate_path",
    "format_and_truncate_tool_result",
    "format_json_compact",
    "proper_join",
    "truncate_text",
]


