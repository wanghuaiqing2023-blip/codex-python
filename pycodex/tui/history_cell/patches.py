"""Patch summaries and image-tool transcript helpers.

Upstream source: ``codex/codex-rs/tui/src/history_cell/patches.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from .._porting import RustTuiModule
from ..line_truncation import Line, Span
from ..exec_cell.render import CommandOutput, OutputLinesParams, TOOL_CALL_MAX_LINES, output_lines
from .base import PlainHistoryCell, plain_lines

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::patches",
    source="codex/codex-rs/tui/src/history_cell/patches.rs",
)

RAW_DIFF_SUMMARY_WIDTH = 10_000
PATCH_FAILURE_TITLE = "Failed to apply patch"
VIEWED_IMAGE_TITLE = "Viewed Image"
GENERATED_IMAGE_TITLE = "Generated Image:"


def line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


def _display_path_for(path: str | Path, cwd: str | Path) -> str:
    path_obj = Path(path)
    cwd_obj = Path(cwd)
    try:
        return str(path_obj.relative_to(cwd_obj)).replace("\\", "/")
    except Exception:
        return str(path_obj).replace("\\", "/")


def _file_url(path: str | Path) -> str:
    text = str(path)
    if text.startswith("/"):
        return "file://" + quote(text)
    try:
        return Path(text).absolute().as_uri()
    except Exception:
        return text


def _change_kind(change: Any) -> str:
    if isinstance(change, str):
        return change
    if isinstance(change, dict):
        for key in ("kind", "type", "status", "change_type"):
            if key in change:
                return str(change[key])
    for attr in ("kind", "type", "status", "change_type"):
        value = getattr(change, attr, None)
        if value is not None:
            return str(value)
    return "modified"


def _change_marker(kind: str) -> str:
    normalized = kind.lower()
    if "add" in normalized or "create" in normalized or normalized == "a":
        return "A"
    if "delete" in normalized or "remove" in normalized or normalized == "d":
        return "D"
    if "rename" in normalized or "move" in normalized or normalized == "r":
        return "R"
    return "M"


def create_diff_summary(
    changes: Mapping[str | Path, Any], cwd: str | Path, wrap_cols: int
) -> list[Line]:
    """Module-local semantic fallback for Rust ``create_diff_summary``.

    The full Rust helper lives in ``diff_render.rs``.  Until that renderer is
    fully ported, this preserves the history-cell contract that a patch event
    displays deterministic file-level summary lines.
    """

    del wrap_cols
    rows: list[Line] = []
    for path, change in sorted(changes.items(), key=lambda item: str(item[0])):
        marker = _change_marker(_change_kind(change))
        display = _display_path_for(path, cwd)
        move_path = None
        if isinstance(change, dict):
            move_path = change.get("move_path") or change.get("new_path") or change.get("to")
        else:
            move_path = (
                getattr(change, "move_path", None)
                or getattr(change, "new_path", None)
                or getattr(change, "to", None)
            )
        if move_path:
            display = f"{display} -> {_display_path_for(move_path, cwd)}"
        rows.append(Line.from_text(f"{marker} {display}"))
    return rows


@dataclass
class PatchHistoryCell:
    changes: Mapping[str | Path, Any] = field(default_factory=dict)
    cwd: Path = field(default_factory=lambda: Path("."))

    def display_lines(self, width: int) -> list[Line]:
        return create_diff_summary(self.changes, self.cwd, int(width))

    def raw_lines(self) -> list[Line]:
        return plain_lines(create_diff_summary(self.changes, self.cwd, RAW_DIFF_SUMMARY_WIDTH))


def new_patch_event(
    changes: Mapping[str | Path, Any], cwd: str | Path
) -> PatchHistoryCell:
    return PatchHistoryCell(dict(changes), Path(cwd))


def new_patch_apply_failure(stderr: str) -> PlainHistoryCell:
    lines = [Line.from_spans([Span(PATCH_FAILURE_TITLE, "magenta bold")])]
    if str(stderr).strip():
        output = output_lines(
            CommandOutput(exit_code=1, formatted_output="", aggregated_output=str(stderr)),
            OutputLinesParams(
                line_limit=TOOL_CALL_MAX_LINES,
                only_err=True,
                include_angle_pipe=True,
                include_prefix=True,
            ),
        )
        lines.extend(output.lines)
    return PlainHistoryCell.new(lines)


def new_view_image_tool_call(path: str | Path, cwd: str | Path) -> PlainHistoryCell:
    display_path = _display_path_for(path, cwd)
    return PlainHistoryCell.new(
        [
            Line.from_text(VIEWED_IMAGE_TITLE),
            Line.from_text(f"  | {display_path}"),
        ]
    )


def new_image_generation_call(
    call_id: str,
    revised_prompt: str | None = None,
    saved_path: str | Path | None = None,
) -> PlainHistoryCell:
    detail = str(revised_prompt) if revised_prompt is not None else str(call_id)
    lines = [
        Line.from_text(GENERATED_IMAGE_TITLE),
        Line.from_text(f"  | {detail}"),
    ]
    if saved_path is not None:
        lines.append(Line.from_text(f"  | Saved to: {_file_url(saved_path)}"))
    return PlainHistoryCell.new(lines)


def display_lines(cell: PatchHistoryCell | PlainHistoryCell, width: int) -> list[Line]:
    return cell.display_lines(width)


def raw_lines(cell: PatchHistoryCell | PlainHistoryCell) -> list[Line]:
    return cell.raw_lines()


__all__ = [
    "GENERATED_IMAGE_TITLE",
    "PATCH_FAILURE_TITLE",
    "PatchHistoryCell",
    "RAW_DIFF_SUMMARY_WIDTH",
    "RUST_MODULE",
    "VIEWED_IMAGE_TITLE",
    "create_diff_summary",
    "display_lines",
    "line_text",
    "new_image_generation_call",
    "new_patch_apply_failure",
    "new_patch_event",
    "new_view_image_tool_call",
    "raw_lines",
]
