"""Theme-derived styling for the configurable footer status line.

Python port of Rust ``codex-tui::bottom_pane::status_line_style``.

The Rust module returns ratatui ``Line``/``Span``/``Style`` values.  Python keeps
the same user-visible contract as a small semantic model: ordered spans with
text, foreground color, and modifiers such as ``dim`` and ``underlined``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Optional, Tuple, Union

from .._porting import RustTuiModule
from ..style import Color
from ..style import Style

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::status_line_style",
    source="codex/codex-rs/tui/src/bottom_pane/status_line_style.rs",
    status="complete",
)

STATUS_LINE_SEPARATOR = " · "
STATUS_LINE_COLOR_SATURATION_PERCENT = 85
STATUS_LINE_COLOR_BRIGHTNESS_PERCENT = 100


@dataclass(frozen=True)
class StyledSpan:
    """Semantic equivalent of a ratatui span for status-line tests."""

    text: str
    style: Style = field(default_factory=Style)


@dataclass(frozen=True)
class StyledLine:
    """Semantic equivalent of a ratatui line for status-line tests."""

    spans: Tuple[StyledSpan, ...]

    @property
    def text(self) -> str:
        return line_text(self)


class StatusLineAccent(Enum):
    MODEL = "Model"
    PATH = "Path"
    BRANCH = "Branch"
    STATE = "State"
    USAGE = "Usage"
    LIMIT = "Limit"
    METADATA = "Metadata"
    MODE = "Mode"
    THREAD = "Thread"
    PROGRESS = "Progress"

    @classmethod
    def for_item(cls, item: Any) -> "StatusLineAccent":
        name = _item_name(item)
        if name in {"ModelName", "ModelWithReasoning"}:
            return cls.MODEL
        if name in {"CurrentDir", "ProjectRoot"}:
            return cls.PATH
        if name in {"GitBranch", "PullRequestNumber", "BranchChanges"}:
            return cls.BRANCH
        if name == "Status":
            return cls.STATE
        if name in {
            "ContextRemaining",
            "ContextUsed",
            "ContextWindowSize",
            "UsedTokens",
            "TotalInputTokens",
            "TotalOutputTokens",
        }:
            return cls.USAGE
        if name in {"FiveHourLimit", "WeeklyLimit"}:
            return cls.LIMIT
        if name in {"CodexVersion", "SessionId"}:
            return cls.METADATA
        if name in {"FastMode", "RawOutput", "Permissions", "ApprovalMode"}:
            return cls.MODE
        if name == "ThreadTitle":
            return cls.THREAD
        if name == "TaskProgress":
            return cls.PROGRESS
        raise ValueError(f"unknown StatusLineItem: {item!r}")

    def scopes(self) -> tuple[str, ...]:
        return {
            StatusLineAccent.MODEL: ("entity.name.type", "support.type", "variable"),
            StatusLineAccent.PATH: ("string", "markup.underline.link"),
            StatusLineAccent.BRANCH: ("entity.name.function", "entity.name.tag"),
            StatusLineAccent.STATE: ("keyword.control", "keyword"),
            StatusLineAccent.USAGE: ("constant.numeric", "constant"),
            StatusLineAccent.LIMIT: ("constant.language", "storage.type"),
            StatusLineAccent.METADATA: ("comment", "constant.other"),
            StatusLineAccent.MODE: ("storage.modifier", "keyword.operator"),
            StatusLineAccent.THREAD: ("markup.heading", "entity.name.section"),
            StatusLineAccent.PROGRESS: ("markup.inserted", "constant.numeric"),
        }[self]

    def fallback_style(self) -> Style:
        if self in {
            StatusLineAccent.MODEL,
            StatusLineAccent.STATE,
            StatusLineAccent.METADATA,
            StatusLineAccent.MODE,
        }:
            return Style().with_fg(Color.named("cyan"))
        if self in {StatusLineAccent.PATH, StatusLineAccent.USAGE, StatusLineAccent.PROGRESS}:
            return Style().with_fg(Color.named("green"))
        return Style().with_fg(Color.named("magenta"))


def status_line_from_segments(
    segments: Iterable[Tuple[Any, str]],
    use_theme_colors: bool,
) -> Optional[StyledLine]:
    return status_line_from_segments_with_resolver(segments, use_theme_colors, lambda _accent: None)


def status_line_from_segments_with_resolver(
    segments: Iterable[Tuple[Any, str]],
    use_theme_colors: bool,
    theme_style_for_accent: Callable[[StatusLineAccent], Optional[Style]],
) -> Optional[StyledLine]:
    spans: List[StyledSpan] = []
    for item, text in segments:
        if spans:
            spans.append(StyledSpan(STATUS_LINE_SEPARATOR, Style().dim()))

        if use_theme_colors:
            accent = StatusLineAccent.for_item(item)
            style = soften_status_line_style(theme_style_for_accent(accent) or accent.fallback_style())
        else:
            style = Style().dim()

        if _item_name(item) == "PullRequestNumber":
            style = _with_modifier(style, "underlined")

        spans.append(StyledSpan(str(text), style))

    if not spans:
        return None
    return StyledLine(tuple(spans))


def soften_status_line_style(style: Style) -> Style:
    if style.fg is None:
        return style
    return Style(
        fg=soften_status_line_color(style.fg),
        bg=style.bg,
        modifiers=style.modifiers,
    )


def soften_status_line_color(color: Union[Color, str, Tuple[int, int, int]]) -> Union[Color, str, Tuple[int, int, int]]:
    parsed = _parse_color(color)
    if isinstance(parsed, Color):
        if parsed.kind == "rgb":
            return Color.rgb(_soften_rgb(parsed.value))
        if parsed.kind == "named":
            mapped = _soften_named_color(str(parsed.value))
            return Color.named(mapped)
        return parsed
    if isinstance(parsed, tuple):
        return _soften_rgb(parsed)
    if isinstance(parsed, str):
        return _soften_named_color(parsed)
    return parsed


def weighted_luma(r: int, g: int, b: int) -> int:
    return (77 * _u8(r, "r") + 150 * _u8(g, "g") + 29 * _u8(b, "b")) // 256


def soften_rgb_channel(channel: int, luma: int) -> int:
    channel = _u8(channel, "channel")
    if luma < 0:
        raise ValueError("luma must be non-negative")
    softened = (
        channel * STATUS_LINE_COLOR_SATURATION_PERCENT
        + int(luma) * (100 - STATUS_LINE_COLOR_SATURATION_PERCENT)
        + 50
    ) // 100
    return (softened * STATUS_LINE_COLOR_BRIGHTNESS_PERCENT + 50) // 100


def line_text(line: StyledLine) -> str:
    return "".join(span.text for span in line.spans)


def _item_name(item: Any) -> str:
    if isinstance(item, str):
        return item
    name = getattr(item, "name", None)
    if isinstance(name, str):
        return _rust_case(name)
    value = getattr(item, "value", None)
    if isinstance(value, str):
        return _rust_case(value)
    return _rust_case(str(item))


def _rust_case(name: str) -> str:
    parts = name.replace("-", "_").split("_")
    if len(parts) > 1:
        return "".join(part[:1].upper() + part[1:].lower() for part in parts if part)
    return name[:1].upper() + name[1:] if name and name[0].islower() else name


def _with_modifier(style: Style, modifier: str) -> Style:
    return Style(fg=style.fg, bg=style.bg, modifiers=style.modifiers | frozenset({modifier}))


def _parse_color(color: Union[Color, str, Tuple[int, int, int]]) -> Union[Color, str, Tuple[int, int, int]]:
    if isinstance(color, Color):
        return color
    if isinstance(color, tuple):
        if len(color) != 3:
            raise ValueError("rgb color must contain three channels")
        return (_u8(color[0], "r"), _u8(color[1], "g"), _u8(color[2], "b"))
    return color


def _soften_rgb(rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    r, g, b = (_u8(rgb[0], "r"), _u8(rgb[1], "g"), _u8(rgb[2], "b"))
    luma = weighted_luma(r, g, b)
    return (
        soften_rgb_channel(r, luma),
        soften_rgb_channel(g, luma),
        soften_rgb_channel(b, luma),
    )


def _soften_named_color(name: str) -> str:
    mapping = {
        "LightRed": "Red",
        "light_red": "red",
        "lightred": "red",
        "LightGreen": "Green",
        "light_green": "green",
        "lightgreen": "green",
        "LightYellow": "Yellow",
        "light_yellow": "yellow",
        "lightyellow": "yellow",
        "LightBlue": "Blue",
        "light_blue": "blue",
        "lightblue": "blue",
        "LightMagenta": "Magenta",
        "light_magenta": "magenta",
        "lightmagenta": "magenta",
        "LightCyan": "Cyan",
        "light_cyan": "cyan",
        "lightcyan": "cyan",
        "White": "Gray",
        "white": "gray",
    }
    return mapping.get(name, name)


def _u8(value: int, name: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0 or value > 255:
        raise ValueError(f"{name} must fit in u8")
    return value


__all__ = [
    "RUST_MODULE",
    "STATUS_LINE_COLOR_BRIGHTNESS_PERCENT",
    "STATUS_LINE_COLOR_SATURATION_PERCENT",
    "STATUS_LINE_SEPARATOR",
    "StatusLineAccent",
    "StyledLine",
    "StyledSpan",
    "line_text",
    "soften_rgb_channel",
    "soften_status_line_color",
    "soften_status_line_style",
    "status_line_from_segments",
    "status_line_from_segments_with_resolver",
    "weighted_luma",
]

