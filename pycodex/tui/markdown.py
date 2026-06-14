"""Markdown entry points and fence normalization for ``codex-tui::markdown``.

Rust source: ``codex/codex-rs/tui/src/markdown.rs``.

This module owns the conservative `````md``/`````markdown`` fence unwrapping
used before agent markdown is handed to the renderer.  Full pulldown-cmark to
ratatui rendering remains owned by ``pycodex.tui.markdown_render``; these entry
points delegate there instead of fabricating renderer behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ._porting import RustTuiModule
from . import table_detect

RUST_MODULE = RustTuiModule(crate="codex-tui", module="markdown", source="codex/codex-rs/tui/src/markdown.rs")


@dataclass(frozen=True)
class Fence:
    marker: str
    length: int
    is_blockquoted: bool = False


@dataclass
class MarkdownCandidateData:
    fence: Fence
    opening_range: range
    content_ranges: list[range] = field(default_factory=list)


class ActiveFenceKind(Enum):
    PASSTHROUGH = "passthrough"
    MARKDOWN_CANDIDATE = "markdown_candidate"


@dataclass
class ActiveFence:
    kind: ActiveFenceKind
    fence: Fence | None = None
    candidate: MarkdownCandidateData | None = None

    @classmethod
    def passthrough(cls, fence: Fence) -> "ActiveFence":
        return cls(ActiveFenceKind.PASSTHROUGH, fence=fence)

    @classmethod
    def markdown_candidate(cls, data: MarkdownCandidateData) -> "ActiveFence":
        return cls(ActiveFenceKind.MARKDOWN_CANDIDATE, candidate=data)


def append_markdown(markdown_source: str, width: int | None = None, cwd: Any = None, lines: list[Any] | None = None) -> list[Any]:
    """Render markdown through the markdown_render dependency and append lines."""
    from . import markdown_render

    rendered = markdown_render.render_markdown_text_with_width_and_cwd(markdown_source, width, cwd)
    rendered_lines = getattr(rendered, "lines", rendered)
    if lines is None:
        lines = []
    lines.extend(list(rendered_lines))
    return lines


def append_markdown_agent(markdown_source: str, width: int | None = None, lines: list[Any] | None = None) -> list[Any]:
    """Normalize agent markdown fences, then delegate to ``append_markdown``."""
    return append_markdown(unwrap_markdown_fences(markdown_source), width, None, lines)


def render_markdown_agent_with_links_and_cwd(markdown_source: str, width: int | None = None, cwd: Any = None) -> Any:
    """Normalize agent markdown fences, then delegate to hyperlink markdown rendering."""
    from . import markdown_render

    return markdown_render.render_markdown_lines_with_width_and_cwd(unwrap_markdown_fences(markdown_source), width, cwd)


def unwrap_markdown_fences(markdown_source: str) -> str:
    """Strip markdown fences that contain markdown table syntax.

    Only ``md``/``markdown`` fences whose complete body contains adjacent table
    header + delimiter rows are unwrapped.  Other fences, markdown fences without
    tables, and unclosed markdown fences are preserved exactly.
    """
    source = str(markdown_source)
    if "```" not in source and "~~~" not in source:
        return source

    out: list[str] = []
    active: ActiveFence | None = None
    offset = 0

    def push_source_range(source_range: range) -> None:
        if source_range.start != source_range.stop:
            out.append(source[source_range.start : source_range.stop])

    for line in source.splitlines(keepends=True):
        line_start = offset
        offset += len(line)
        line_range = range(line_start, offset)

        if active is not None:
            current = active
            active = None
            if current.kind is ActiveFenceKind.PASSTHROUGH:
                assert current.fence is not None
                push_source_range(line_range)
                if not is_close_fence(line, current.fence):
                    active = current
                continue

            assert current.candidate is not None
            data = current.candidate
            if is_close_fence(line, data.fence):
                content = content_from_ranges(source, data.content_ranges)
                if markdown_fence_contains_table(content, data.fence.is_blockquoted):
                    for content_range in data.content_ranges:
                        push_source_range(content_range)
                else:
                    push_source_range(data.opening_range)
                    for content_range in data.content_ranges:
                        push_source_range(content_range)
                    push_source_range(line_range)
            else:
                data.content_ranges.append(line_range)
                active = ActiveFence.markdown_candidate(data)
            continue

        parsed = parse_open_fence(line)
        if parsed is not None:
            fence, is_markdown = parsed
            if is_markdown:
                active = ActiveFence.markdown_candidate(MarkdownCandidateData(fence, line_range, []))
            else:
                push_source_range(line_range)
                active = ActiveFence.passthrough(fence)
            continue

        push_source_range(line_range)

    if active is not None:
        if active.kind is ActiveFenceKind.MARKDOWN_CANDIDATE and active.candidate is not None:
            push_source_range(active.candidate.opening_range)
            for content_range in active.candidate.content_ranges:
                push_source_range(content_range)
        # Passthrough fences were emitted as lines arrived, matching Rust.

    return "".join(out)


def strip_line_indent(line: str) -> str | None:
    """Strip trailing newline and up to three leading columns of indent."""
    without_newline = line[:-1] if line.endswith("\n") else line
    byte_idx = 0
    column = 0
    for ch in without_newline:
        if ch == " ":
            byte_idx += 1
            column += 1
        elif ch == "\t":
            byte_idx += 1
            column += 4
        else:
            break
        if column >= 4:
            return None
    return without_newline[byte_idx:]


def parse_open_fence(line: str) -> tuple[Fence, bool] | None:
    trimmed = strip_line_indent(line)
    if trimmed is None:
        return None
    is_blockquoted = trimmed.lstrip().startswith(">")
    fence_scan_text = table_detect.strip_blockquote_prefix(trimmed)
    marker = table_detect.parse_fence_marker(fence_scan_text)
    if marker is None:
        return None
    marker_char, marker_len = marker
    return Fence(marker_char, marker_len, is_blockquoted), table_detect.is_markdown_fence_info(fence_scan_text, marker_len)


def is_close_fence(line: str, fence: Fence) -> bool:
    trimmed = strip_line_indent(line)
    if trimmed is None:
        return False
    if fence.is_blockquoted:
        if not trimmed.lstrip().startswith(">"):
            return False
        fence_scan_text = table_detect.strip_blockquote_prefix(trimmed)
    else:
        fence_scan_text = trimmed
    marker = table_detect.parse_fence_marker(fence_scan_text)
    if marker is None:
        return False
    marker_char, marker_len = marker
    return marker_char == fence.marker and marker_len >= fence.length and fence_scan_text[marker_len:].strip() == ""


def markdown_fence_contains_table(content: str, is_blockquoted_fence: bool) -> bool:
    previous_line: str | None = None
    for line in content.splitlines():
        text = table_detect.strip_blockquote_prefix(line) if is_blockquoted_fence else line
        trimmed = text.strip()
        if not trimmed:
            previous_line = None
            continue
        if (
            previous_line is not None
            and table_detect.is_table_header_line(previous_line)
            and not table_detect.is_table_delimiter_line(previous_line)
            and table_detect.is_table_delimiter_line(trimmed)
        ):
            return True
        previous_line = trimmed
    return False


def content_from_ranges(source: str, ranges: list[range]) -> str:
    return "".join(source[source_range.start : source_range.stop] for source_range in ranges)


# Lightweight helpers mirroring Rust test-only functions for Python parity tests.
def lines_to_strings(lines: list[Any]) -> list[str]:
    out: list[str] = []
    for line in lines:
        spans = getattr(line, "spans", None)
        if spans is None:
            out.append(str(line))
        else:
            out.append("".join(str(getattr(span, "content", span)) for span in spans))
    return out


def append_markdown_agent_unwraps_blockquoted_markdown_fence_table() -> str:
    return unwrap_markdown_fences("> ```markdown\n> | A | B |\n> |---|---|\n> | 1 | 2 |\n> ```\n")


def append_markdown_agent_keeps_non_blockquoted_markdown_fence_with_blockquote_table_example() -> str:
    src = "```markdown\n> | A | B |\n> |---|---|\n> | 1 | 2 |\n```\n"
    return unwrap_markdown_fences(src)


def unwrap_markdown_fences_repro_keeps_fence_without_header_delimiter_pair() -> str:
    src = "```markdown\n| A | B |\nnot a delimiter row\n| --- | --- |\n# Heading\n```\n"
    return unwrap_markdown_fences(src)


__all__ = [
    "ActiveFence",
    "ActiveFenceKind",
    "Fence",
    "MarkdownCandidateData",
    "RUST_MODULE",
    "append_markdown",
    "append_markdown_agent",
    "append_markdown_agent_keeps_non_blockquoted_markdown_fence_with_blockquote_table_example",
    "append_markdown_agent_unwraps_blockquoted_markdown_fence_table",
    "content_from_ranges",
    "is_close_fence",
    "lines_to_strings",
    "markdown_fence_contains_table",
    "parse_open_fence",
    "render_markdown_agent_with_links_and_cwd",
    "strip_line_indent",
    "unwrap_markdown_fences",
    "unwrap_markdown_fences_repro_keeps_fence_without_header_delimiter_pair",
]
