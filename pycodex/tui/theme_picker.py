"""Semantic syntax-theme picker helpers for the TUI port.

Rust counterpart: ``codex-rs/tui/src/theme_picker.rs``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple, Union

from .render import highlight
from .ratatui_bridge import Buffer, Color, Line, Rect, Span, Style


class PreviewDiffKind(str, Enum):
    CONTEXT = "context"
    ADDED = "added"
    REMOVED = "removed"


class DiffLineType(str, Enum):
    CONTEXT = "context"
    INSERT = "insert"
    DELETE = "delete"


@dataclass(frozen=True)
class PreviewRow:
    line_no: int
    kind: PreviewDiffKind
    code: str


NARROW_PREVIEW_ROWS: Tuple[PreviewRow, ...] = (
    PreviewRow(12, PreviewDiffKind.CONTEXT, "fn greet(name: &str) -> String {"),
    PreviewRow(13, PreviewDiffKind.REMOVED, '    format!("Hello, {}!", name)'),
    PreviewRow(13, PreviewDiffKind.ADDED, '    format!("Hello, {name}!")'),
    PreviewRow(14, PreviewDiffKind.CONTEXT, "}"),
)

WIDE_PREVIEW_ROWS: Tuple[PreviewRow, ...] = (
    PreviewRow(31, PreviewDiffKind.CONTEXT, "fn summarize(users: &[User]) -> String {"),
    PreviewRow(32, PreviewDiffKind.REMOVED, "    let active = users.iter().filter(|u| u.is_active).count();"),
    PreviewRow(32, PreviewDiffKind.ADDED, "    let active = users.iter().filter(|u| u.is_active()).count();"),
    PreviewRow(33, PreviewDiffKind.CONTEXT, "    let names: Vec<&str> = users.iter().map(User::name).take(3).collect();"),
    PreviewRow(34, PreviewDiffKind.REMOVED, '    format!("{} active: {}", active, names.join(", "))'),
    PreviewRow(34, PreviewDiffKind.ADDED, '    format!("{active} active users: {}", names.join(", "))'),
    PreviewRow(35, PreviewDiffKind.ADDED, "        .trim()"),
    PreviewRow(36, PreviewDiffKind.CONTEXT, "}"),
)

WIDE_PREVIEW_MIN_WIDTH = 44
WIDE_PREVIEW_LEFT_INSET = 2
PREVIEW_FRAME_PADDING = 1
PREVIEW_FALLBACK_SUBTITLE = "Move up/down to live preview themes"
DEFAULT_TERMINAL_WIDTH = 80
DEFAULT_BUNDLED_THEMES = ("light-plus", "dark-plus", "github-light", "github-dark")


@dataclass(frozen=True)
class ThemeEntry:
    name: str
    is_custom: bool = False


@dataclass(frozen=True)
class SelectionItem:
    name: str
    is_current: bool = False
    dismiss_on_select: bool = True
    search_value: Optional[str] = None
    action_event: Optional[str] = None


@dataclass
class SelectionViewParams:
    title: Optional[str] = None
    subtitle: Optional[str] = None
    footer_hint: Optional[str] = None
    items: List[SelectionItem] = field(default_factory=list)
    is_searchable: bool = True
    search_placeholder: Optional[str] = None
    initial_selected_idx: Optional[int] = None
    side_content: Optional[object] = None
    side_content_width: str = "half"
    side_content_min_width: int = WIDE_PREVIEW_MIN_WIDTH
    stacked_side_content: Optional[object] = None
    preserve_side_content_bg: bool = True
    on_selection_changed: Optional[Callable[[int], Optional[str]]] = None
    on_cancel: Optional[Callable[[], str]] = None


@dataclass(frozen=True)
class RenderedPreviewLine:
    line_no: int
    marker: str
    code: str
    x: int
    y: int
    diff_type: DiffLineType
    dim: bool = False

    def text(self) -> str:
        return " " * self.x + f"{self.line_no} {self.marker}{self.code}"


def preview_diff_line_type(kind: Union[PreviewDiffKind, str]) -> DiffLineType:
    value = PreviewDiffKind(kind)
    if value == PreviewDiffKind.ADDED:
        return DiffLineType.INSERT
    if value == PreviewDiffKind.REMOVED:
        return DiffLineType.DELETE
    return DiffLineType.CONTEXT


def _marker(kind: PreviewDiffKind) -> str:
    if kind == PreviewDiffKind.ADDED:
        return "+"
    if kind == PreviewDiffKind.REMOVED:
        return "-"
    return " "


def centered_offset(available: int, content: int, min_frame: int) -> int:
    free = max(int(available) - int(content), 0)
    frame = int(min_frame) if free >= int(min_frame) * 2 else 0
    return frame + max(free - frame * 2, 0) // 2


def render_preview(
    width: int,
    height: int,
    preview_rows: Sequence[PreviewRow],
    center_vertically: bool,
    left_inset: int,
) -> List[RenderedPreviewLine]:
    if width <= 0 or height <= 0 or not preview_rows:
        return []
    content_height = min(len(preview_rows), height)
    left_pad = min(max(left_inset, 0), max(width - 1, 0))
    top_pad = centered_offset(height, content_height, PREVIEW_FRAME_PADDING) if center_vertically else 0
    rendered: List[RenderedPreviewLine] = []
    for idx, row in enumerate(preview_rows[:content_height]):
        y = top_pad + idx
        if y >= height:
            break
        rendered.append(
            RenderedPreviewLine(
                line_no=row.line_no,
                marker=_marker(row.kind),
                code=row.code[: max(width - left_pad, 0)],
                x=left_pad,
                y=y,
                diff_type=preview_diff_line_type(row.kind),
                dim=row.kind == PreviewDiffKind.REMOVED,
            )
        )
    return rendered


def _semantic_style_to_bridge(style: object) -> Style:
    bridge = Style.default()
    fg = getattr(style, "fg", None)
    if fg is not None:
        kind = getattr(fg, "kind", "")
        value = getattr(fg, "value", None)
        if kind == "rgb" and isinstance(value, tuple) and len(value) == 3:
            bridge = bridge.with_fg(Color.rgb(int(value[0]), int(value[1]), int(value[2])))
        elif kind == "named" and value is not None:
            bridge = bridge.with_fg(str(value))
        elif kind == "indexed" and isinstance(value, int):
            bridge = bridge.with_fg(Color.indexed(value))
    if getattr(style, "bold", False):
        bridge = bridge.bold()
    if getattr(style, "italic", False):
        bridge = bridge.italic()
    return bridge


def preview_line_to_bridge_line(line: RenderedPreviewLine, syntax_spans: Optional[List[object]] = None) -> Line:
    base = Style.default()
    line_no_style = base.dim()
    marker_style = base
    code_style = base
    if line.diff_type == DiffLineType.INSERT:
        marker_style = base.with_fg("green").bold()
        code_style = base.with_fg("green")
    elif line.diff_type == DiffLineType.DELETE:
        marker_style = base.with_fg("red").bold()
        code_style = base.with_fg("red").dim()
    spans = [
        Span.raw(" " * line.x),
        Span.styled(str(line.line_no), line_no_style),
        Span.raw(" "),
        Span.styled(line.marker, marker_style),
    ]
    if syntax_spans:
        for span in syntax_spans:
            text = getattr(span, "text", "")
            if text:
                syntax_style = _semantic_style_to_bridge(getattr(span, "style", object()))
                spans.append(Span.styled(text, code_style.patch(syntax_style)))
    else:
        spans.append(Span.styled(line.code, code_style))
    return Line.from_spans(spans)


def render_preview_to_buffer(
    area: Rect,
    buf: Buffer,
    preview_rows: Sequence[PreviewRow],
    center_vertically: bool,
    left_inset: int,
) -> None:
    if area.width <= 0 or area.height <= 0:
        return
    preview_lines = render_preview(
        area.width,
        area.height,
        preview_rows,
        center_vertically=center_vertically,
        left_inset=left_inset,
    )
    preview_code = "\n".join(row.code for row in preview_rows)
    syntax_lines = highlight.highlight_code_to_styled_spans(preview_code, "rust")
    for index, preview_line in enumerate(preview_lines):
        syntax_spans = syntax_lines[index] if syntax_lines is not None and index < len(syntax_lines) else None
        line = preview_line_to_bridge_line(preview_line, syntax_spans)
        buf.set_line(area.x, area.y + preview_line.y, line, max_width=area.width)


@dataclass(frozen=True)
class ThemePreviewWideRenderable:
    def desired_height(self, _width: int) -> int:
        return 65535

    def render_lines(self, width: int, height: int) -> List[RenderedPreviewLine]:
        return render_preview(width, height, WIDE_PREVIEW_ROWS, True, WIDE_PREVIEW_LEFT_INSET)

    def render(self, area: Rect, buf: Buffer) -> None:
        render_preview_to_buffer(
            area,
            buf,
            WIDE_PREVIEW_ROWS,
            center_vertically=True,
            left_inset=WIDE_PREVIEW_LEFT_INSET,
        )

    def render_ref(self, area: Rect, buf: Buffer) -> None:
        self.render(area, buf)


@dataclass(frozen=True)
class ThemePreviewNarrowRenderable:
    def desired_height(self, _width: int) -> int:
        return len(NARROW_PREVIEW_ROWS)

    def render_lines(self, width: int, height: Optional[int] = None) -> List[RenderedPreviewLine]:
        return render_preview(width, height or len(NARROW_PREVIEW_ROWS), NARROW_PREVIEW_ROWS, False, 0)

    def render(self, area: Rect, buf: Buffer) -> None:
        render_preview_to_buffer(
            area,
            buf,
            NARROW_PREVIEW_ROWS,
            center_vertically=False,
            left_inset=0,
        )

    def render_ref(self, area: Rect, buf: Buffer) -> None:
        self.render(area, buf)


def popup_content_width(width: int) -> int:
    return max(min(int(width), 120) - 4, 0)


def side_by_side_layout_widths(
    content_width: int,
    side_min_width: int = WIDE_PREVIEW_MIN_WIDTH,
) -> Optional[Tuple[int, int]]:
    if content_width < 40 + side_min_width:
        return None
    side_width = content_width // 2
    list_width = content_width - side_width
    if list_width < 40 or side_width < side_min_width:
        return None
    return (list_width, side_width)


def subtitle_available_width(terminal_width: Optional[int]) -> int:
    return popup_content_width(terminal_width or DEFAULT_TERMINAL_WIDTH)


def _display_path(path: Path) -> str:
    try:
        home = Path.home().resolve()
        resolved = path.resolve()
        relative = resolved.relative_to(home)
        return "~" if str(relative) == "." else "~/" + str(relative).replace(os.sep, "/")
    except Exception:
        return str(path)


def theme_picker_subtitle(
    codex_home: Optional[Union[str, Path]],
    terminal_width: Optional[int] = None,
) -> str:
    if terminal_width is not None and int(terminal_width) < 120:
        return PREVIEW_FALLBACK_SUBTITLE
    available_width = subtitle_available_width(terminal_width)
    if codex_home is not None:
        path = _display_path(Path(codex_home) / "themes")
        if path.startswith("~"):
            subtitle = f"Custom .tmTheme files can be added to the {path} directory."
            if len(subtitle) <= available_width:
                return subtitle
    return PREVIEW_FALLBACK_SUBTITLE


def list_available_themes(codex_home: Optional[Union[str, Path]] = None) -> List[ThemeEntry]:
    entries = [ThemeEntry(name) for name in DEFAULT_BUNDLED_THEMES]
    if codex_home is not None:
        themes_dir = Path(codex_home) / "themes"
        if themes_dir.exists():
            for path in sorted(themes_dir.glob("*.tmTheme")):
                entries.append(ThemeEntry(path.stem, is_custom=True))
    return entries


def configured_theme_name() -> str:
    return DEFAULT_BUNDLED_THEMES[0]


def build_theme_picker_params(
    current_name: Optional[str] = None,
    codex_home: Optional[Union[str, Path]] = None,
    terminal_width: Optional[int] = None,
) -> SelectionViewParams:
    entries = list_available_themes(codex_home)
    available_names = {entry.name for entry in entries}
    effective_name = current_name if current_name in available_names else configured_theme_name()
    initial_idx: Optional[int] = None
    items: List[SelectionItem] = []
    for idx, entry in enumerate(entries):
        display_name = f"{entry.name} (custom)" if entry.is_custom else entry.name
        is_current = entry.name == effective_name
        if is_current:
            initial_idx = idx
        items.append(
            SelectionItem(
                name=display_name,
                is_current=is_current,
                dismiss_on_select=True,
                search_value=entry.name,
                action_event=f"SyntaxThemeSelected:{entry.name}",
            )
        )

    preview_names = [item.search_value for item in items]

    def on_selection_changed(idx: int) -> Optional[str]:
        if 0 <= idx < len(preview_names) and preview_names[idx] is not None:
            return f"SyntaxThemePreviewed:{preview_names[idx]}"
        return None

    def on_cancel() -> str:
        return "SyntaxThemePreviewed:restore-original"

    return SelectionViewParams(
        title="Select Syntax Theme",
        subtitle=theme_picker_subtitle(codex_home, terminal_width),
        footer_hint="enter select   esc cancel",
        items=items,
        is_searchable=True,
        search_placeholder="Type to filter themes...",
        initial_selected_idx=initial_idx,
        side_content=ThemePreviewWideRenderable(),
        side_content_width="half",
        side_content_min_width=WIDE_PREVIEW_MIN_WIDTH,
        stacked_side_content=ThemePreviewNarrowRenderable(),
        preserve_side_content_bg=True,
        on_selection_changed=on_selection_changed,
        on_cancel=on_cancel,
    )


def preview_line_number(line: str) -> Optional[int]:
    stripped = line.lstrip()
    digits = ""
    for char in stripped:
        if char.isdigit():
            digits += char
        else:
            break
    if not digits or not stripped[len(digits) :].startswith(" "):
        return None
    return int(digits)


def preview_line_marker(line: str) -> Optional[str]:
    stripped = line.lstrip()
    digits_len = len(stripped) - len(stripped.lstrip("0123456789"))
    if digits_len == 0 or len(stripped) <= digits_len + 1 or stripped[digits_len] != " ":
        return None
    return stripped[digits_len + 1]


__all__ = [
    "DEFAULT_BUNDLED_THEMES",
    "DiffLineType",
    "NARROW_PREVIEW_ROWS",
    "PREVIEW_FALLBACK_SUBTITLE",
    "PREVIEW_FRAME_PADDING",
    "PreviewDiffKind",
    "PreviewRow",
    "RenderedPreviewLine",
    "SelectionItem",
    "SelectionViewParams",
    "ThemeEntry",
    "ThemePreviewNarrowRenderable",
    "ThemePreviewWideRenderable",
    "WIDE_PREVIEW_LEFT_INSET",
    "WIDE_PREVIEW_MIN_WIDTH",
    "WIDE_PREVIEW_ROWS",
    "build_theme_picker_params",
    "centered_offset",
    "configured_theme_name",
    "list_available_themes",
    "preview_diff_line_type",
    "preview_line_marker",
    "preview_line_number",
    "preview_line_to_bridge_line",
    "render_preview",
    "render_preview_to_buffer",
    "side_by_side_layout_widths",
    "subtitle_available_width",
    "theme_picker_subtitle",
]
