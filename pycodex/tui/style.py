"""Style helpers for TUI rendering.

Upstream source: ``codex/codex-rs/tui/src/style.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ._porting import RustTuiModule
from .color import Rgb
from .color import blend
from .color import is_light

RUST_MODULE = RustTuiModule(crate="codex-tui", module="style", source="codex/codex-rs/tui/src/style.rs")

LIGHT_BG_ACCENT_RGB: Rgb = (0, 95, 135)
TABLE_SEPARATOR_FG_ALPHA: float = 0.20


class StdoutColorLevel(Enum):
    TRUE_COLOR = "TrueColor"
    ANSI256 = "Ansi256"
    ANSI16 = "Ansi16"
    UNKNOWN = "Unknown"


@dataclass(frozen=True)
class Color:
    """Semantic color value used by the Python TUI render model."""

    kind: str
    value: Rgb | str

    @classmethod
    def rgb(cls, rgb: Rgb) -> "Color":
        return cls("rgb", rgb)

    @classmethod
    def named(cls, name: str) -> "Color":
        return cls("named", name)


CYAN = Color.named("cyan")


@dataclass(frozen=True)
class Style:
    """Small semantic equivalent of ratatui ``Style`` for this module."""

    fg: Color | None = None
    bg: Color | None = None
    modifiers: frozenset[str] = field(default_factory=frozenset)

    def with_fg(self, color: Color) -> "Style":
        return Style(fg=color, bg=self.bg, modifiers=self.modifiers)

    def with_bg(self, color: Color) -> "Style":
        return Style(fg=self.fg, bg=color, modifiers=self.modifiers)

    def bold(self) -> "Style":
        return Style(fg=self.fg, bg=self.bg, modifiers=self.modifiers | frozenset({"bold"}))

    def dim(self) -> "Style":
        return Style(fg=self.fg, bg=self.bg, modifiers=self.modifiers | frozenset({"dim"}))


def rgb_color(rgb: Rgb) -> Color:
    return Color.rgb(rgb)


def best_color(rgb: Rgb) -> Color:
    """Semantic stand-in for Rust palette selection.

    The exact terminal palette reduction belongs to ``terminal_palette``. For
    module-level style parity, callers can still compare the selected semantic
    RGB target.
    """

    return Color.rgb(rgb)


def default_bg() -> Rgb | None:
    return None


def default_fg() -> Rgb | None:
    return None


def stdout_color_level() -> StdoutColorLevel:
    return StdoutColorLevel.UNKNOWN


def user_message_style() -> Style:
    return user_message_style_for(default_bg())


def proposed_plan_style() -> Style:
    return proposed_plan_style_for(default_bg())


def table_separator_style() -> Style:
    return table_separator_style_for(default_fg(), default_bg(), stdout_color_level())


def accent_style() -> Style:
    return accent_style_for(default_bg())


def user_message_style_for(terminal_bg: Rgb | None) -> Style:
    if terminal_bg is None:
        return Style()
    return Style().with_bg(user_message_bg(terminal_bg))


def proposed_plan_style_for(terminal_bg: Rgb | None) -> Style:
    if terminal_bg is None:
        return Style()
    return Style().with_bg(proposed_plan_bg(terminal_bg))


def accent_style_for(terminal_bg: Rgb | None) -> Style:
    if terminal_bg is not None and is_light(terminal_bg):
        return Style().with_fg(best_color(LIGHT_BG_ACCENT_RGB)).bold()
    return Style().with_fg(CYAN).bold()


def table_separator_style_for(
    terminal_fg: Rgb | None,
    terminal_bg: Rgb | None,
    color_level: StdoutColorLevel,
) -> Style:
    if terminal_fg is None or terminal_bg is None:
        return Style().dim()
    separator_rgb = blend(terminal_fg, terminal_bg, TABLE_SEPARATOR_FG_ALPHA)
    if color_level is StdoutColorLevel.TRUE_COLOR:
        return Style().with_fg(rgb_color(separator_rgb))
    if color_level is StdoutColorLevel.ANSI256:
        return Style().with_fg(best_color(separator_rgb))
    return Style().dim()


def user_message_bg(terminal_bg: Rgb) -> Color:
    top: Rgb
    alpha: float
    if is_light(terminal_bg):
        top, alpha = (0, 0, 0), 0.04
    else:
        top, alpha = (255, 255, 255), 0.12
    return best_color(blend(top, terminal_bg, alpha))


def proposed_plan_bg(terminal_bg: Rgb) -> Color:
    return user_message_bg(terminal_bg)


__all__ = [
    "CYAN",
    "Color",
    "LIGHT_BG_ACCENT_RGB",
    "RUST_MODULE",
    "StdoutColorLevel",
    "Style",
    "TABLE_SEPARATOR_FG_ALPHA",
    "accent_style",
    "accent_style_for",
    "best_color",
    "default_bg",
    "default_fg",
    "proposed_plan_bg",
    "proposed_plan_style",
    "proposed_plan_style_for",
    "rgb_color",
    "stdout_color_level",
    "table_separator_style",
    "table_separator_style_for",
    "user_message_bg",
    "user_message_style",
    "user_message_style_for",
]
