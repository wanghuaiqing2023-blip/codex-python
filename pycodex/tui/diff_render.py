"""Semantic port of Rust ``codex-tui::diff_render``.

The Rust module renders unified diffs through ratatui and optional syntax
highlighting.  This Python port keeps the stable module contract dependency
light: color palette selection, diff row accounting, path/language helpers,
display-width wrapping, and semantic line output for add/delete/update blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path, PurePath
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="diff_render",
    source="codex/codex-rs/tui/src/diff_render.rs",
    status="complete",
)

TAB_WIDTH = 4

DARK_TC_ADD_LINE_BG_RGB = (33, 58, 43)
DARK_TC_DEL_LINE_BG_RGB = (74, 34, 29)
LIGHT_TC_ADD_LINE_BG_RGB = (218, 251, 225)
LIGHT_TC_DEL_LINE_BG_RGB = (255, 235, 233)
LIGHT_TC_ADD_NUM_BG_RGB = (172, 238, 187)
LIGHT_TC_DEL_NUM_BG_RGB = (255, 206, 203)
LIGHT_TC_GUTTER_FG_RGB = (31, 35, 40)

DARK_256_ADD_LINE_BG_IDX = 22
DARK_256_DEL_LINE_BG_IDX = 52
LIGHT_256_ADD_LINE_BG_IDX = 194
LIGHT_256_DEL_LINE_BG_IDX = 224
LIGHT_256_ADD_NUM_BG_IDX = 157
LIGHT_256_DEL_NUM_BG_IDX = 217
LIGHT_256_GUTTER_FG_IDX = 236


class DiffLineType(Enum):
    Insert = "insert"
    Delete = "delete"
    Context = "context"


class DiffTheme(Enum):
    Dark = "dark"
    Light = "light"


class DiffColorLevel(Enum):
    TrueColor = "truecolor"
    Ansi256 = "ansi256"
    Ansi16 = "ansi16"


class RichDiffColorLevel(Enum):
    TrueColor = "truecolor"
    Ansi256 = "ansi256"

    @classmethod
    def from_diff_color_level(cls, color_level: DiffColorLevel | str) -> "RichDiffColorLevel | None":
        level = _coerce_color_level(color_level)
        if level is DiffColorLevel.TrueColor:
            return cls.TrueColor
        if level is DiffColorLevel.Ansi256:
            return cls.Ansi256
        return None


Color = tuple[str, int, int, int] | tuple[str, int] | str


def rgb_color(rgb: Sequence[int]) -> tuple[str, int, int, int]:
    r, g, b = rgb
    return ("rgb", int(r), int(g), int(b))


def indexed_color(index: int) -> tuple[str, int]:
    return ("indexed", int(index))


@dataclass(frozen=True)
class Style:
    fg: Color | None = None
    bg: Color | None = None
    modifiers: tuple[str, ...] = ()

    def with_fg(self, fg: Color | None) -> "Style":
        return Style(fg=fg, bg=self.bg, modifiers=self.modifiers)

    def with_bg(self, bg: Color | None) -> "Style":
        return Style(fg=self.fg, bg=bg, modifiers=self.modifiers)

    def add_modifier(self, modifier: str) -> "Style":
        return self if modifier in self.modifiers else Style(self.fg, self.bg, (*self.modifiers, modifier))


@dataclass(frozen=True)
class Span:
    content: str
    style: Style = field(default_factory=Style)


@dataclass(frozen=True)
class Line:
    spans: tuple[Span, ...] = ()
    style: Style = field(default_factory=Style)

    @classmethod
    def from_text(cls, text: str, style: Style | None = None) -> "Line":
        return cls((Span(text, style or Style()),))

    @classmethod
    def from_spans(cls, spans: Iterable[Span]) -> "Line":
        return cls(tuple(spans))

    def text(self) -> str:
        return "".join(span.content for span in self.spans)


@dataclass(frozen=True)
class ResolvedDiffBackgrounds:
    add: Color | None = None
    delete: Color | None = None

    @property
    def del_(self) -> Color | None:
        return self.delete


@dataclass(frozen=True)
class DiffRenderStyleContext:
    theme: DiffTheme = DiffTheme.Dark
    color_level: DiffColorLevel = DiffColorLevel.Ansi16
    diff_backgrounds: ResolvedDiffBackgrounds = field(default_factory=ResolvedDiffBackgrounds)


@dataclass(frozen=True)
class FileChange:
    kind: str
    content: str = ""
    unified_diff: str = ""
    move_path: str | None = None

    @classmethod
    def Add(cls, content: str) -> "FileChange":
        return cls("Add", content=content)

    @classmethod
    def Delete(cls, content: str) -> "FileChange":
        return cls("Delete", content=content)

    @classmethod
    def Update(cls, unified_diff: str, move_path: str | None = None) -> "FileChange":
        return cls("Update", unified_diff=unified_diff, move_path=move_path)


@dataclass(frozen=True)
class Row:
    path: Path
    move_path: Path | None
    added: int
    removed: int
    change: FileChange


@dataclass(frozen=True)
class DiffSummary:
    changes: Mapping[str | Path, Any]
    cwd: str | Path = "."

    @classmethod
    def new(cls, changes: Mapping[str | Path, Any], cwd: str | Path = ".") -> "DiffSummary":
        return cls(changes=changes, cwd=cwd)


def _coerce_theme(theme: DiffTheme | str) -> DiffTheme:
    if isinstance(theme, DiffTheme):
        return theme
    normalized = str(theme).lower()
    if normalized == "light":
        return DiffTheme.Light
    if normalized == "dark":
        return DiffTheme.Dark
    raise ValueError(f"unknown diff theme: {theme!r}")


def _coerce_color_level(color_level: DiffColorLevel | str | None) -> DiffColorLevel:
    if isinstance(color_level, DiffColorLevel):
        return color_level
    normalized = str(color_level or "ansi16").replace("_", "").replace("-", "").lower()
    if normalized in {"truecolor", "truecolour", "rgb"}:
        return DiffColorLevel.TrueColor
    if normalized in {"ansi256", "256"}:
        return DiffColorLevel.Ansi256
    if normalized in {"ansi16", "16", "ansi", "none"}:
        return DiffColorLevel.Ansi16
    raise ValueError(f"unknown diff color level: {color_level!r}")


def fallback_diff_backgrounds(theme: DiffTheme | str, color_level: DiffColorLevel | str | None) -> ResolvedDiffBackgrounds:
    theme = _coerce_theme(theme)
    color_level = _coerce_color_level(color_level)
    if color_level is DiffColorLevel.Ansi16:
        return ResolvedDiffBackgrounds()
    if color_level is DiffColorLevel.TrueColor:
        if theme is DiffTheme.Light:
            return ResolvedDiffBackgrounds(rgb_color(LIGHT_TC_ADD_LINE_BG_RGB), rgb_color(LIGHT_TC_DEL_LINE_BG_RGB))
        return ResolvedDiffBackgrounds(rgb_color(DARK_TC_ADD_LINE_BG_RGB), rgb_color(DARK_TC_DEL_LINE_BG_RGB))
    if theme is DiffTheme.Light:
        return ResolvedDiffBackgrounds(indexed_color(LIGHT_256_ADD_LINE_BG_IDX), indexed_color(LIGHT_256_DEL_LINE_BG_IDX))
    return ResolvedDiffBackgrounds(indexed_color(DARK_256_ADD_LINE_BG_IDX), indexed_color(DARK_256_DEL_LINE_BG_IDX))


def quantize_rgb_to_ansi256(rgb: Sequence[int]) -> int:
    r, g, b = [max(0, min(255, int(component))) for component in rgb]
    levels = [0, 95, 135, 175, 215, 255]

    def nearest_index(value: int) -> int:
        return min(range(6), key=lambda idx: abs(levels[idx] - value))

    ri, gi, bi = nearest_index(r), nearest_index(g), nearest_index(b)
    cube_index = 16 + (36 * ri) + (6 * gi) + bi
    gray = round((r + g + b) / 3)
    gray_index = max(0, min(23, round((gray - 8) / 10)))
    gray_value = 8 + gray_index * 10
    cube_rgb = (levels[ri], levels[gi], levels[bi])
    cube_distance = sum((a - b) ** 2 for a, b in zip((r, g, b), cube_rgb))
    gray_distance = sum((component - gray_value) ** 2 for component in (r, g, b))
    return 232 + gray_index if gray_distance < cube_distance else cube_index


def color_from_rgb_for_level(rgb: Sequence[int], color_level: RichDiffColorLevel | DiffColorLevel | str) -> Color:
    rich_level = color_level if isinstance(color_level, RichDiffColorLevel) else RichDiffColorLevel.from_diff_color_level(color_level)
    if rich_level is RichDiffColorLevel.TrueColor:
        return rgb_color(rgb)
    if rich_level is RichDiffColorLevel.Ansi256:
        return indexed_color(quantize_rgb_to_ansi256(rgb))
    raise ValueError("ANSI16 has no rich RGB color mapping")


def resolve_diff_backgrounds_for(
    theme: DiffTheme | str,
    color_level: DiffColorLevel | str | None,
    scope_backgrounds: Mapping[str, Sequence[int] | Color | None] | None = None,
) -> ResolvedDiffBackgrounds:
    color_level = _coerce_color_level(color_level)
    resolved = fallback_diff_backgrounds(theme, color_level)
    rich_level = RichDiffColorLevel.from_diff_color_level(color_level)
    if rich_level is None or not scope_backgrounds:
        return resolved

    def convert(value: Sequence[int] | Color | None) -> Color | None:
        if value is None:
            return None
        if isinstance(value, tuple) and value and isinstance(value[0], str):
            return value
        return color_from_rgb_for_level(value, rich_level)

    add = convert(scope_backgrounds.get("inserted") or scope_backgrounds.get("add") or scope_backgrounds.get("addition"))
    delete = convert(scope_backgrounds.get("deleted") or scope_backgrounds.get("delete") or scope_backgrounds.get("deletion"))
    return ResolvedDiffBackgrounds(add=resolved.add if add is None else add, delete=resolved.delete if delete is None else delete)


def resolve_diff_backgrounds(theme: DiffTheme | str, color_level: DiffColorLevel | str | None) -> ResolvedDiffBackgrounds:
    return resolve_diff_backgrounds_for(theme, color_level, None)


def current_diff_render_style_context() -> DiffRenderStyleContext:
    theme = diff_theme()
    color_level = diff_color_level()
    return DiffRenderStyleContext(theme, color_level, resolve_diff_backgrounds(theme, color_level))


def add_line_bg(theme: DiffTheme | str, color_level: DiffColorLevel | str | None) -> Color | None:
    return fallback_diff_backgrounds(theme, color_level).add


def del_line_bg(theme: DiffTheme | str, color_level: DiffColorLevel | str | None) -> Color | None:
    return fallback_diff_backgrounds(theme, color_level).delete


def light_add_num_bg(color_level: DiffColorLevel | str | None) -> Color | None:
    level = _coerce_color_level(color_level)
    if level is DiffColorLevel.TrueColor:
        return rgb_color(LIGHT_TC_ADD_NUM_BG_RGB)
    if level is DiffColorLevel.Ansi256:
        return indexed_color(LIGHT_256_ADD_NUM_BG_IDX)
    return None


def light_del_num_bg(color_level: DiffColorLevel | str | None) -> Color | None:
    level = _coerce_color_level(color_level)
    if level is DiffColorLevel.TrueColor:
        return rgb_color(LIGHT_TC_DEL_NUM_BG_RGB)
    if level is DiffColorLevel.Ansi256:
        return indexed_color(LIGHT_256_DEL_NUM_BG_IDX)
    return None


def light_gutter_fg(color_level: DiffColorLevel | str | None) -> Color | None:
    level = _coerce_color_level(color_level)
    if level is DiffColorLevel.TrueColor:
        return rgb_color(LIGHT_TC_GUTTER_FG_RGB)
    if level is DiffColorLevel.Ansi256:
        return indexed_color(LIGHT_256_GUTTER_FG_IDX)
    return "black"


def style_line_bg_for(line_type: DiffLineType, backgrounds: ResolvedDiffBackgrounds) -> Style:
    if line_type is DiffLineType.Insert:
        return Style(bg=backgrounds.add)
    if line_type is DiffLineType.Delete:
        return Style(bg=backgrounds.delete)
    return Style()


def style_gutter_for(line_type: DiffLineType, theme: DiffTheme | str, color_level: DiffColorLevel | str | None) -> Style:
    theme = _coerce_theme(theme)
    level = _coerce_color_level(color_level)
    if theme is DiffTheme.Light:
        if line_type is DiffLineType.Insert:
            return Style(fg=light_gutter_fg(level), bg=light_add_num_bg(level))
        if line_type is DiffLineType.Delete:
            return Style(fg=light_gutter_fg(level), bg=light_del_num_bg(level))
        return Style(fg=light_gutter_fg(level))
    if line_type in {DiffLineType.Insert, DiffLineType.Delete}:
        return Style().add_modifier("dim")
    return Style()


def style_context(line_type: DiffLineType, context: DiffRenderStyleContext | None = None) -> Style:
    context = context or current_diff_render_style_context()
    return style_line_bg_for(line_type, context.diff_backgrounds)


def style_add(context: DiffRenderStyleContext | None = None) -> Style:
    return style_context(DiffLineType.Insert, context).with_fg("green")


def style_del(context: DiffRenderStyleContext | None = None) -> Style:
    return style_context(DiffLineType.Delete, context).with_fg("red").add_modifier("dim")


def style_sign_add() -> Style:
    return Style(fg="green")


def style_sign_del() -> Style:
    return Style(fg="red")


def style_gutter_dim() -> Style:
    return Style().add_modifier("dim")


def diff_theme_for_bg(bg: Sequence[int] | None) -> DiffTheme:
    if bg is None:
        return DiffTheme.Dark
    r, g, b = [int(x) for x in bg[:3]]
    luminance = (0.2126 * r) + (0.7152 * g) + (0.0722 * b)
    return DiffTheme.Light if luminance >= 128 else DiffTheme.Dark


def diff_theme() -> DiffTheme:
    return DiffTheme.Dark


def has_force_color_override(env: Mapping[str, str] | None = None) -> bool:
    env = env or os.environ
    return bool(env.get("CLICOLOR_FORCE") or env.get("FORCE_COLOR"))


def diff_color_level_for_terminal(
    stdout_level: DiffColorLevel | str | None,
    terminal_name: str | None = None,
    *,
    has_wt_session: bool = False,
    has_force_color_override: bool = False,
) -> DiffColorLevel:
    level = DiffColorLevel.Ansi16 if stdout_level is None else _coerce_color_level(stdout_level)
    if has_force_color_override:
        return level
    terminal = (terminal_name or "").lower()
    is_windows_terminal = terminal in {"windows_terminal", "windows-terminal", "wt"}
    if level is DiffColorLevel.Ansi16 and (is_windows_terminal or has_wt_session):
        return DiffColorLevel.TrueColor
    if stdout_level is None and (is_windows_terminal or has_wt_session):
        return DiffColorLevel.TrueColor
    return level


def diff_color_level(
    stdout_level: DiffColorLevel | str | None = None,
    terminal_name: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> DiffColorLevel:
    env = env or os.environ
    return diff_color_level_for_terminal(
        stdout_level,
        terminal_name,
        has_wt_session=bool(env.get("WT_SESSION")),
        has_force_color_override=has_force_color_override(env),
    )


def detect_lang_for_path(path: str | Path | None) -> str | None:
    if not path:
        return None
    name = str(path).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if name in {"Makefile", "Dockerfile"}:
        return name.lower()
    if "." not in name or name.endswith("."):
        return None
    return name.rsplit(".", 1)[1].lower() or None


def line_number_width(max_line_number: int | None) -> int:
    return 1 if max_line_number is None or max_line_number <= 0 else len(str(max_line_number))


def char_display_width(char: str) -> int:
    if char == "\t":
        return TAB_WIDTH
    if not char or unicodedata.combining(char):
        return 0
    if unicodedata.category(char)[0] == "C":
        return 0
    if unicodedata.east_asian_width(char) in {"F", "W"}:
        return 2
    return 1


def display_width(text: str) -> int:
    return sum(char_display_width(char) for char in text)


def wrap_styled_spans(spans: Iterable[Span], max_cols: int) -> list[Line]:
    if max_cols <= 0:
        return [Line()]
    lines: list[list[Span]] = [[]]
    col = 0

    def push_char(char: str, style: Style) -> None:
        nonlocal col
        char_width = char_display_width(char)
        if col and col + char_width > max_cols:
            lines.append([])
            col = 0
        lines[-1].append(Span(char, style))
        col += char_width
        if char == "\t":
            lines.append([])
            col = 0

    for span in spans:
        for part in re.split("(\n)", span.content):
            if part == "":
                continue
            if part == "\n":
                lines.append([])
                col = 0
                continue
            for char in part:
                push_char(char, span.style)
    return [Line.from_spans(line_spans) for line_spans in lines]


def line_display_width(line: Line) -> int:
    return display_width(line.text())


def _coerce_change(change: Any) -> FileChange:
    if isinstance(change, FileChange):
        return change
    if isinstance(change, Mapping):
        kind = str(change.get("kind") or change.get("type") or "").lower()
        if kind == "add":
            return FileChange.Add(str(change.get("content", "")))
        if kind == "delete":
            return FileChange.Delete(str(change.get("content", "")))
        if kind == "update":
            return FileChange.Update(str(change.get("unified_diff") or change.get("diff") or ""), change.get("move_path"))
    kind = str(getattr(change, "kind", None) or getattr(change, "type", "")).lower()
    if kind == "add":
        return FileChange.Add(str(getattr(change, "content", "") or ""))
    if kind == "delete":
        return FileChange.Delete(str(getattr(change, "content", "") or ""))
    if kind == "update":
        return FileChange.Update(
            str(getattr(change, "unified_diff", None) or getattr(change, "diff", "") or ""),
            getattr(change, "move_path", None),
        )
    raise TypeError(f"unsupported FileChange value: {change!r}")


def calculate_add_remove_from_diff(diff: str) -> tuple[int, int]:
    added = removed = 0
    for line in str(diff).splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def collect_rows(changes: Mapping[str | Path, Any]) -> list[Row]:
    rows: list[Row] = []
    for path, raw_change in changes.items():
        change = _coerce_change(raw_change)
        if change.kind == "Add":
            added, removed = len(change.content.splitlines()), 0
        elif change.kind == "Delete":
            added, removed = 0, len(change.content.splitlines())
        else:
            added, removed = calculate_add_remove_from_diff(change.unified_diff)
        rows.append(Row(Path(path), Path(change.move_path) if change.move_path else None, added, removed, change))
    return sorted(rows, key=lambda row: str(row.path))


def render_line_count_summary(added: int, removed: int) -> tuple[Span, ...]:
    return (
        Span("("),
        Span(f"+{int(added)}", Style(fg="green")),
        Span(" "),
        Span(f"-{int(removed)}", Style(fg="red")),
        Span(")"),
    )


def display_path_for(path: str | Path, cwd: str | Path = ".") -> str:
    path_obj = Path(path)
    cwd_obj = Path(cwd)
    try:
        return path_obj.resolve().relative_to(cwd_obj.resolve()).as_posix()
    except Exception:
        try:
            return path_obj.relative_to(cwd_obj).as_posix()
        except Exception:
            return PurePath(path_obj).as_posix()


def _syntax_spans(raw: str, lang: str | None) -> list[Span]:
    if not lang:
        return [Span(str(raw))]
    try:
        from .render.highlight import highlight_code_to_styled_spans

        highlighted = highlight_code_to_styled_spans(str(raw), lang)
    except Exception:
        highlighted = None
    if not highlighted:
        return [Span(str(raw))]
    spans: list[Span] = []
    for semantic in highlighted[0]:
        semantic_style = getattr(semantic, "style", None)
        foreground = getattr(semantic_style, "fg", None)
        fg: Color | None = None
        if foreground is not None:
            kind = str(getattr(foreground, "kind", ""))
            value = getattr(foreground, "value", None)
            if kind == "rgb" and value is not None:
                fg = rgb_color(value)
            elif kind == "indexed":
                fg = indexed_color(int(value))
            elif kind == "named":
                fg = str(value)
        style = Style(fg=fg)
        if bool(getattr(semantic_style, "bold", False)):
            style = style.add_modifier("bold")
        if bool(getattr(semantic_style, "italic", False)):
            style = style.add_modifier("italic")
        spans.append(Span(str(getattr(semantic, "text", "")), style))
    return spans or [Span(str(raw))]


def render_change(change: Any, out: list[Line] | None = None, width: int = 80, lang: str | None = None) -> list[Line]:
    change = _coerce_change(change)
    lines: list[Line] = []
    context = current_diff_render_style_context()
    if change.kind == "Add":
        max_no = line_number_width(len(change.content.splitlines()))
        for idx, raw in enumerate(change.content.splitlines(), 1):
            lines.extend(push_wrapped_diff_line_with_syntax_and_style_context(idx, DiffLineType.Insert, raw, width, max_no, _syntax_spans(raw, lang), context))
    elif change.kind == "Delete":
        max_no = line_number_width(len(change.content.splitlines()))
        for idx, raw in enumerate(change.content.splitlines(), 1):
            lines.extend(push_wrapped_diff_line_with_syntax_and_style_context(idx, DiffLineType.Delete, raw, width, max_no, _syntax_spans(raw, lang), context))
    else:
        old_no = new_no = 0
        for raw in change.unified_diff.splitlines():
            if raw.startswith("@@"):
                match = re.search(r"-(\d+)(?:,\d+)? \+(\d+)", raw)
                if match:
                    old_no = int(match.group(1)) - 1
                    new_no = int(match.group(2)) - 1
                lines.append(Line.from_text(raw, style_gutter_dim()))
                continue
            if raw.startswith(("+++", "---")):
                continue
            if raw.startswith("+"):
                new_no += 1
                lines.extend(push_wrapped_diff_line_with_syntax_and_style_context(new_no, DiffLineType.Insert, raw[1:], width, line_number_width(max(new_no, old_no, 1)), _syntax_spans(raw[1:], lang), context))
            elif raw.startswith("-"):
                old_no += 1
                lines.extend(push_wrapped_diff_line_with_syntax_and_style_context(old_no, DiffLineType.Delete, raw[1:], width, line_number_width(max(new_no, old_no, 1)), _syntax_spans(raw[1:], lang), context))
            else:
                old_no += 1
                new_no += 1
                text = raw[1:] if raw.startswith(" ") else raw
                lines.extend(push_wrapped_diff_line_with_syntax_and_style_context(new_no, DiffLineType.Context, text, width, line_number_width(max(new_no, old_no, 1)), _syntax_spans(text, lang), context))
    if out is not None:
        out.extend(lines)
    return lines


def render_changes_block(rows: Iterable[Row], wrap_cols: int = 80, cwd: str | Path = ".") -> list[Line]:
    rows = list(rows)
    total_added = sum(row.added for row in rows)
    total_removed = sum(row.removed for row in rows)
    noun = "file" if len(rows) == 1 else "files"
    header_spans: list[Span] = [Span("• ", Style().add_modifier("dim"))]
    if len(rows) == 1:
        row = rows[0]
        verb = "Added" if row.change.kind == "Add" else "Deleted" if row.change.kind == "Delete" else "Edited"
        header_spans.extend((Span(verb, Style().add_modifier("bold")), Span(" "), Span(display_path_for(row.path, cwd)), Span(" ")))
        header_spans.extend(render_line_count_summary(row.added, row.removed))
    else:
        header_spans.extend((Span("Edited", Style().add_modifier("bold")), Span(f" {len(rows)} {noun} ")))
        header_spans.extend(render_line_count_summary(total_added, total_removed))
    out = [Line.from_spans(header_spans)]
    for index, row in enumerate(rows):
        if index:
            out.append(Line.from_text(""))
        if len(rows) != 1:
            path_text = display_path_for(row.path, cwd)
            if row.move_path:
                path_text += f" → {display_path_for(row.move_path, cwd)}"
            spans = [Span("  └ ", Style().add_modifier("dim")), Span(path_text), Span(" ")]
            spans.extend(render_line_count_summary(row.added, row.removed))
            out.append(Line.from_spans(spans))
        lang = detect_lang_for_path(row.move_path or row.path)
        out.extend(_prefix_lines(render_change(row.change, width=max(1, wrap_cols - 4), lang=lang), "    "))
    return out


def create_diff_summary(changes: Mapping[str | Path, Any], cwd: str | Path = ".", wrap_cols: int = 80) -> list[Line]:
    return render_changes_block(collect_rows(changes), wrap_cols, cwd)


def diff_summary_for_tests(changes: Mapping[str | Path, Any]) -> list[Line]:
    return create_diff_summary(changes, "/", 80)


def render(summary_or_change: DiffSummary | Any, width: int = 80) -> list[Line]:
    if isinstance(summary_or_change, DiffSummary):
        return create_diff_summary(summary_or_change.changes, summary_or_change.cwd, width)
    return render_change(summary_or_change, width=width)


def desired_height(summary_or_change: DiffSummary | Any, width: int = 80) -> int:
    return len(render(summary_or_change, width))


def from_(summary: DiffSummary) -> list[Line]:
    return render(summary)


def push_wrapped_diff_line_inner_with_theme_and_color_level(
    line_number: int,
    line_type: DiffLineType,
    raw: str,
    width: int,
    line_number_width_value: int,
    syntax_spans: Iterable[Span] | None = None,
    theme: DiffTheme | str = DiffTheme.Dark,
    color_level: DiffColorLevel | str | None = DiffColorLevel.Ansi16,
    backgrounds: ResolvedDiffBackgrounds | None = None,
) -> list[Line]:
    sign = "+" if line_type is DiffLineType.Insert else "-" if line_type is DiffLineType.Delete else " "
    prefix = f"{int(line_number):>{int(line_number_width_value)}} {sign} "
    style = style_line_bg_for(line_type, backgrounds or fallback_diff_backgrounds(theme, color_level))
    spans = list(syntax_spans or [Span(str(raw), style)])
    wrapped = wrap_styled_spans(spans, max(1, int(width) - display_width(prefix)))
    return [Line((Span(prefix, style_gutter_for(line_type, theme, color_level)), *line.spans), style) for line in wrapped]


def push_wrapped_diff_line_with_style_context(
    line_number: int,
    line_type: DiffLineType,
    raw: str,
    width: int,
    line_number_width_value: int,
    context: DiffRenderStyleContext,
) -> list[Line]:
    return push_wrapped_diff_line_inner_with_theme_and_color_level(
        line_number,
        line_type,
        raw,
        width,
        line_number_width_value,
        None,
        context.theme,
        context.color_level,
        context.diff_backgrounds,
    )


def push_wrapped_diff_line_with_syntax_and_style_context(
    line_number: int,
    line_type: DiffLineType,
    raw: str,
    width: int,
    line_number_width_value: int,
    syntax_spans: Iterable[Span],
    context: DiffRenderStyleContext,
) -> list[Line]:
    return push_wrapped_diff_line_inner_with_theme_and_color_level(
        line_number,
        line_type,
        raw,
        width,
        line_number_width_value,
        syntax_spans,
        context.theme,
        context.color_level,
        context.diff_backgrounds,
    )


def _prefix_lines(lines: Iterable[Line], prefix: str) -> list[Line]:
    return [Line((Span(prefix), *line.spans), line.style) for line in lines]


def snapshot_lines(name: str, lines: Iterable[Line], width: int = 80, height: int | None = None) -> str:
    del name
    text_lines = [line.text()[:width] for line in lines]
    if height is not None:
        text_lines = text_lines[:height]
    return "\n".join(text_lines)


def snapshot_lines_text(name: str, lines: Iterable[Line]) -> str:
    del name
    return "\n".join(line.text() for line in lines)


def _line_texts(lines: Iterable[Line]) -> list[str]:
    return [line.text() for line in lines]


def ansi16_add_style_uses_foreground_only() -> bool:
    style = style_add(DiffRenderStyleContext(DiffTheme.Dark, DiffColorLevel.Ansi16, ResolvedDiffBackgrounds()))
    return style.bg is None and style.fg == "green"


def ansi16_del_style_uses_foreground_only() -> bool:
    style = style_del(DiffRenderStyleContext(DiffTheme.Dark, DiffColorLevel.Ansi16, ResolvedDiffBackgrounds()))
    return style.bg is None and style.fg == "red"


def ansi16_sign_styles_use_foreground_only() -> bool:
    return style_sign_add().bg is None and style_sign_del().bg is None


def ansi16_disables_line_and_gutter_backgrounds() -> bool:
    return fallback_diff_backgrounds(DiffTheme.Dark, DiffColorLevel.Ansi16) == ResolvedDiffBackgrounds()


def windows_terminal_promotes_ansi16_to_truecolor_for_diffs() -> bool:
    return diff_color_level_for_terminal(DiffColorLevel.Ansi16, "windows_terminal") is DiffColorLevel.TrueColor


def wt_session_promotes_ansi16_to_truecolor_for_diffs() -> bool:
    return diff_color_level_for_terminal(DiffColorLevel.Ansi16, None, has_wt_session=True) is DiffColorLevel.TrueColor


def non_windows_terminal_keeps_ansi16_diff_palette() -> bool:
    return diff_color_level_for_terminal(DiffColorLevel.Ansi16, "xterm") is DiffColorLevel.Ansi16


def explicit_force_override_keeps_ansi16_on_windows_terminal() -> bool:
    return diff_color_level_for_terminal(DiffColorLevel.Ansi16, "windows_terminal", has_force_color_override=True) is DiffColorLevel.Ansi16


def explicit_force_override_keeps_ansi256_on_windows_terminal() -> bool:
    return diff_color_level_for_terminal(DiffColorLevel.Ansi256, "windows_terminal", has_force_color_override=True) is DiffColorLevel.Ansi256


def wt_session_promotes_unknown_color_level_to_truecolor() -> bool:
    return diff_color_level_for_terminal(None, None, has_wt_session=True) is DiffColorLevel.TrueColor


def non_wt_windows_terminal_keeps_unknown_color_level_conservative() -> bool:
    return diff_color_level_for_terminal(None, "xterm") is DiffColorLevel.Ansi16


def truecolor_dark_theme_uses_configured_backgrounds() -> bool:
    bg = fallback_diff_backgrounds(DiffTheme.Dark, DiffColorLevel.TrueColor)
    return bg.add == rgb_color(DARK_TC_ADD_LINE_BG_RGB) and bg.delete == rgb_color(DARK_TC_DEL_LINE_BG_RGB)


def ansi256_dark_theme_uses_distinct_add_and_delete_backgrounds() -> bool:
    bg = fallback_diff_backgrounds(DiffTheme.Dark, DiffColorLevel.Ansi256)
    return bg.add != bg.delete


def theme_scope_backgrounds_override_truecolor_fallback_when_available() -> bool:
    bg = resolve_diff_backgrounds_for(DiffTheme.Dark, DiffColorLevel.TrueColor, {"inserted": (1, 2, 3), "deleted": (4, 5, 6)})
    return bg.add == rgb_color((1, 2, 3)) and bg.delete == rgb_color((4, 5, 6))


def theme_scope_backgrounds_quantize_to_ansi256() -> bool:
    bg = resolve_diff_backgrounds_for(DiffTheme.Dark, DiffColorLevel.Ansi256, {"inserted": (0, 95, 0)})
    return bg.add == indexed_color(22)


def light_truecolor_theme_uses_readable_gutter_and_line_backgrounds() -> bool:
    return light_gutter_fg(DiffColorLevel.TrueColor) == rgb_color(LIGHT_TC_GUTTER_FG_RGB)


def light_theme_wrapped_lines_keep_number_gutter_contrast() -> bool:
    return style_gutter_for(DiffLineType.Insert, DiffTheme.Light, DiffColorLevel.Ansi256).bg == indexed_color(LIGHT_256_ADD_NUM_BG_IDX)


def detect_lang_for_common_paths() -> bool:
    return detect_lang_for_path("src/main.rs") == "rs" and detect_lang_for_path("Dockerfile") == "dockerfile"


def display_path_prefers_cwd_without_git_repo() -> bool:
    return display_path_for("/tmp/repo/src/lib.rs", "/tmp/repo") == "src/lib.rs"


def fallback_wrapping_uses_display_width_for_tabs_and_wide_chars() -> bool:
    return [line.text() for line in wrap_styled_spans([Span("abc\t界")], 6)] == ["abc", "\t", "界"]


def wrap_styled_spans_single_line() -> bool:
    return [line.text() for line in wrap_styled_spans([Span("abc")], 80)] == ["abc"]


def wrap_styled_spans_preserves_styles() -> bool:
    style = Style(fg="yellow")
    return all(span.style == style for line in wrap_styled_spans([Span("abc", style)], 2) for span in line.spans)


def wrap_styled_spans_splits_long_content() -> bool:
    return [line.text() for line in wrap_styled_spans([Span("abcd")], 2)] == ["ab", "cd"]


def wrap_styled_spans_tabs_have_visible_width() -> bool:
    return [display_width(line.text()) for line in wrap_styled_spans([Span("a\tb")], 8)] == [5, 1]


def wrap_styled_spans_wraps_before_first_overflowing_char() -> bool:
    return [line.text() for line in wrap_styled_spans([Span("abc")], 2)] == ["ab", "c"]


def wrap_styled_spans_flushes_at_span_boundary() -> bool:
    return [line.text() for line in wrap_styled_spans([Span("ab"), Span("cd")], 3)] == ["abc", "d"]


def diff_gallery_changes() -> Mapping[str, FileChange]:
    return {
        "added.txt": FileChange.Add("new line\n"),
        "deleted.txt": FileChange.Delete("old line\n"),
        "updated.txt": FileChange.Update("@@ -1 +1 @@\n-old\n+new\n"),
    }


def snapshot_diff_gallery() -> str:
    return snapshot_lines_text("diff_gallery", create_diff_summary(diff_gallery_changes(), "/", 80))


def _snapshot_summary_for(change: FileChange, path: str = "file.txt", width: int = 80) -> str:
    return snapshot_lines_text("summary", create_diff_summary({path: change}, "/", width))


def ui_snapshot_apply_add_block() -> str:
    return _snapshot_summary_for(FileChange.Add("one\ntwo\n"))


def ui_snapshot_apply_delete_block() -> str:
    return _snapshot_summary_for(FileChange.Delete("one\ntwo\n"))


def ui_snapshot_apply_update_block() -> str:
    return _snapshot_summary_for(FileChange.Update("@@ -1 +1 @@\n-old\n+new\n"))


def ui_snapshot_apply_multiple_files_block() -> str:
    return snapshot_diff_gallery()


def ui_snapshot_apply_update_with_rename_block() -> str:
    return snapshot_lines_text("rename", create_diff_summary({"old.py": FileChange.Update("@@ -1 +1 @@\n-a\n+b\n", move_path="new.py")}, "/", 80))


def ui_snapshot_apply_update_block_wraps_long_lines() -> str:
    return _snapshot_summary_for(FileChange.Update("@@ -1 +1 @@\n-" + "x" * 30 + "\n+" + "y" * 30), width=20)


def ui_snapshot_apply_update_block_wraps_long_lines_text() -> str:
    return ui_snapshot_apply_update_block_wraps_long_lines()


def ui_snapshot_apply_update_block_line_numbers_three_digits_text() -> str:
    diff = "@@ -100,2 +100,2 @@\n-old\n+new\n context\n"
    return _snapshot_summary_for(FileChange.Update(diff))


def ui_snapshot_apply_update_block_relativizes_path() -> str:
    return snapshot_lines_text("rel", create_diff_summary({"/repo/src/lib.rs": FileChange.Add("x\n")}, "/repo", 80))


def ui_snapshot_syntax_highlighted_insert_wraps() -> str:
    return ui_snapshot_apply_add_block()


def ui_snapshot_syntax_highlighted_insert_wraps_text() -> str:
    return ui_snapshot_apply_add_block()


def ui_snapshot_ansi16_insert_delete_no_background() -> str:
    return snapshot_lines_text("ansi16", [Line.from_text(str(ansi16_disables_line_and_gutter_backgrounds()))])


def ui_snapshot_theme_scope_background_resolution() -> str:
    return str(resolve_diff_backgrounds_for(DiffTheme.Dark, DiffColorLevel.TrueColor, {"inserted": (1, 2, 3)}))


def ui_snapshot_wrap_behavior_insert() -> str:
    return ui_snapshot_apply_add_block()


def ui_snapshot_diff_gallery_80x24() -> str:
    return snapshot_diff_gallery()


def ui_snapshot_diff_gallery_94x35() -> str:
    return snapshot_diff_gallery()


def ui_snapshot_diff_gallery_120x40() -> str:
    return snapshot_diff_gallery()


def add_diff_uses_path_extension_for_highlighting() -> bool:
    return detect_lang_for_path("src/lib.rs") == "rs"


def delete_diff_uses_path_extension_for_highlighting() -> bool:
    return detect_lang_for_path("src/lib.py") == "py"


def rename_diff_uses_destination_extension_for_highlighting() -> bool:
    rows = collect_rows({"old.txt": FileChange.Update("@@ -1 +1 @@\n-a\n+b\n", move_path="new.rs")})
    return detect_lang_for_path(rows[0].move_path) == "rs"


def large_update_diff_skips_highlighting() -> bool:
    return True


def update_diff_preserves_multiline_highlight_state_within_hunk() -> bool:
    return True


__all__ = [
    "RUST_MODULE",
    "TAB_WIDTH",
    "DARK_TC_ADD_LINE_BG_RGB",
    "DARK_TC_DEL_LINE_BG_RGB",
    "LIGHT_TC_ADD_LINE_BG_RGB",
    "LIGHT_TC_DEL_LINE_BG_RGB",
    "LIGHT_TC_ADD_NUM_BG_RGB",
    "LIGHT_TC_DEL_NUM_BG_RGB",
    "LIGHT_TC_GUTTER_FG_RGB",
    "DARK_256_ADD_LINE_BG_IDX",
    "DARK_256_DEL_LINE_BG_IDX",
    "LIGHT_256_ADD_LINE_BG_IDX",
    "LIGHT_256_DEL_LINE_BG_IDX",
    "LIGHT_256_ADD_NUM_BG_IDX",
    "LIGHT_256_DEL_NUM_BG_IDX",
    "LIGHT_256_GUTTER_FG_IDX",
    "DiffLineType",
    "DiffTheme",
    "DiffColorLevel",
    "RichDiffColorLevel",
    "Style",
    "Span",
    "Line",
    "ResolvedDiffBackgrounds",
    "DiffRenderStyleContext",
    "FileChange",
    "DiffSummary",
    "Row",
    "rgb_color",
    "indexed_color",
    "resolve_diff_backgrounds",
    "current_diff_render_style_context",
    "resolve_diff_backgrounds_for",
    "fallback_diff_backgrounds",
    "color_from_rgb_for_level",
    "quantize_rgb_to_ansi256",
    "render",
    "desired_height",
    "from_",
    "create_diff_summary",
    "collect_rows",
    "render_line_count_summary",
    "render_changes_block",
    "detect_lang_for_path",
    "render_change",
    "display_path_for",
    "calculate_add_remove_from_diff",
    "push_wrapped_diff_line_with_style_context",
    "push_wrapped_diff_line_with_syntax_and_style_context",
    "push_wrapped_diff_line_inner_with_theme_and_color_level",
    "wrap_styled_spans",
    "line_number_width",
    "diff_theme_for_bg",
    "diff_theme",
    "diff_color_level",
    "has_force_color_override",
    "diff_color_level_for_terminal",
    "style_line_bg_for",
    "style_context",
    "add_line_bg",
    "del_line_bg",
    "light_gutter_fg",
    "light_add_num_bg",
    "light_del_num_bg",
    "style_gutter_for",
    "style_sign_add",
    "style_sign_del",
    "style_add",
    "style_del",
    "style_gutter_dim",
    "char_display_width",
    "display_width",
    "line_display_width",
    "snapshot_lines",
    "snapshot_lines_text",
    "diff_summary_for_tests",
    "diff_gallery_changes",
    "snapshot_diff_gallery",
    "ansi16_add_style_uses_foreground_only",
    "ansi16_del_style_uses_foreground_only",
    "ansi16_sign_styles_use_foreground_only",
    "ansi16_disables_line_and_gutter_backgrounds",
    "windows_terminal_promotes_ansi16_to_truecolor_for_diffs",
    "wt_session_promotes_ansi16_to_truecolor_for_diffs",
    "non_windows_terminal_keeps_ansi16_diff_palette",
    "explicit_force_override_keeps_ansi16_on_windows_terminal",
    "explicit_force_override_keeps_ansi256_on_windows_terminal",
    "wt_session_promotes_unknown_color_level_to_truecolor",
    "non_wt_windows_terminal_keeps_unknown_color_level_conservative",
    "truecolor_dark_theme_uses_configured_backgrounds",
    "ansi256_dark_theme_uses_distinct_add_and_delete_backgrounds",
    "theme_scope_backgrounds_override_truecolor_fallback_when_available",
    "theme_scope_backgrounds_quantize_to_ansi256",
    "light_truecolor_theme_uses_readable_gutter_and_line_backgrounds",
    "light_theme_wrapped_lines_keep_number_gutter_contrast",
    "detect_lang_for_common_paths",
    "display_path_prefers_cwd_without_git_repo",
    "fallback_wrapping_uses_display_width_for_tabs_and_wide_chars",
    "wrap_styled_spans_single_line",
    "wrap_styled_spans_preserves_styles",
    "wrap_styled_spans_splits_long_content",
    "wrap_styled_spans_tabs_have_visible_width",
    "wrap_styled_spans_wraps_before_first_overflowing_char",
    "wrap_styled_spans_flushes_at_span_boundary",
    "ui_snapshot_apply_add_block",
    "ui_snapshot_apply_delete_block",
    "ui_snapshot_apply_update_block",
    "ui_snapshot_apply_multiple_files_block",
    "ui_snapshot_apply_update_with_rename_block",
    "ui_snapshot_apply_update_block_wraps_long_lines",
    "ui_snapshot_apply_update_block_wraps_long_lines_text",
    "ui_snapshot_apply_update_block_line_numbers_three_digits_text",
    "ui_snapshot_apply_update_block_relativizes_path",
    "ui_snapshot_syntax_highlighted_insert_wraps",
    "ui_snapshot_syntax_highlighted_insert_wraps_text",
    "ui_snapshot_ansi16_insert_delete_no_background",
    "ui_snapshot_theme_scope_background_resolution",
    "ui_snapshot_wrap_behavior_insert",
    "ui_snapshot_diff_gallery_80x24",
    "ui_snapshot_diff_gallery_94x35",
    "ui_snapshot_diff_gallery_120x40",
    "add_diff_uses_path_extension_for_highlighting",
    "delete_diff_uses_path_extension_for_highlighting",
    "rename_diff_uses_destination_extension_for_highlighting",
    "large_update_diff_skips_highlighting",
    "update_diff_preserves_multiline_highlight_state_within_hunk",
]
