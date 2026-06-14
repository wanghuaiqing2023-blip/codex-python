"""Terminal palette helpers for TUI rendering.

Upstream source: ``codex/codex-rs/tui/src/terminal_palette.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from typing import Iterator

from ._porting import RustTuiModule
from .color import Rgb
from .color import perceptual_distance

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="terminal_palette",
    source="codex/codex-rs/tui/src/terminal_palette.rs",
)


class StdoutColorLevel(Enum):
    TRUE_COLOR = "TrueColor"
    ANSI256 = "Ansi256"
    ANSI16 = "Ansi16"
    UNKNOWN = "Unknown"


@dataclass(frozen=True)
class Color:
    """Semantic equivalent for the subset of ratatui ``Color`` used here."""

    kind: str
    value: Rgb | int | None = None

    @classmethod
    def default(cls) -> "Color":
        return cls("default", None)


@dataclass(frozen=True)
class DefaultColors:
    fg: Rgb
    bg: Rgb


_default_colors_cache: DefaultColors | None = None
_default_colors_attempted = False


def _xterm_colors() -> tuple[Rgb, ...]:
    system: list[Rgb] = [
        (0, 0, 0),
        (128, 0, 0),
        (0, 128, 0),
        (128, 128, 0),
        (0, 0, 128),
        (128, 0, 128),
        (0, 128, 128),
        (192, 192, 192),
        (128, 128, 128),
        (255, 0, 0),
        (0, 255, 0),
        (255, 255, 0),
        (0, 0, 255),
        (255, 0, 255),
        (0, 255, 255),
        (255, 255, 255),
    ]
    levels = [0, 95, 135, 175, 215, 255]
    cube = [(r, g, b) for r in levels for g in levels for b in levels]
    greys = [(8 + i * 10, 8 + i * 10, 8 + i * 10) for i in range(24)]
    return tuple(system + cube + greys)


XTERM_COLORS: tuple[Rgb, ...] = _xterm_colors()


def stdout_color_level() -> StdoutColorLevel:
    """Best-effort Python equivalent of ``supports_color::on_cached(stdout)``."""

    colorterm = os.environ.get("COLORTERM", "").lower()
    term = os.environ.get("TERM", "").lower()
    if colorterm in {"truecolor", "24bit"}:
        return StdoutColorLevel.TRUE_COLOR
    if "256color" in term:
        return StdoutColorLevel.ANSI256
    if term:
        return StdoutColorLevel.ANSI16
    return StdoutColorLevel.UNKNOWN


def rgb_color(rgb: Rgb) -> Color:
    return Color("rgb", _u8_rgb(rgb))


def indexed_color(index: int) -> Color:
    if index < 0 or index > 255:
        raise ValueError("index must fit in u8")
    return Color("indexed", index)


def _u8_rgb(rgb: Rgb) -> Rgb:
    if len(rgb) != 3:
        raise ValueError("rgb color must contain three channels")
    r, g, b = rgb
    for name, channel in (("r", r), ("g", g), ("b", b)):
        if not isinstance(channel, int):
            raise TypeError(f"{name} must be an int")
        if channel < 0 or channel > 255:
            raise ValueError(f"{name} must fit in u8")
    return (r, g, b)


def xterm_fixed_colors() -> Iterator[tuple[int, Rgb]]:
    """Iterate over stable xterm colors, skipping theme-dependent first 16."""

    return iter(enumerate(XTERM_COLORS[16:], start=16))


def best_color(target: Rgb, color_level: StdoutColorLevel | None = None) -> Color:
    """Return the closest color the terminal can display."""

    level = stdout_color_level() if color_level is None else color_level
    if level is StdoutColorLevel.TRUE_COLOR:
        return rgb_color(target)
    if level is StdoutColorLevel.ANSI256:
        index, _ = min(
            xterm_fixed_colors(),
            key=lambda item: perceptual_distance(item[1], target),
        )
        return indexed_color(index)
    return Color.default()


def requery_default_colors() -> None:
    """Refresh cached default colors when a backend can query them.

    The Python port has no terminal probing backend yet, so this is a no-op.
    """

    return None


def set_default_colors_from_startup_probe(colors: DefaultColors | object | None) -> None:
    """Seed the default color cache from startup probe results."""

    global _default_colors_attempted, _default_colors_cache
    if colors is None:
        _default_colors_cache = None
    elif isinstance(colors, DefaultColors):
        _default_colors_cache = colors
    else:
        _default_colors_cache = DefaultColors(
            fg=getattr(colors, "fg"),
            bg=getattr(colors, "bg"),
        )
    _default_colors_attempted = True


def default_colors() -> DefaultColors | None:
    return _default_colors_cache


def default_fg() -> Rgb | None:
    colors = default_colors()
    return colors.fg if colors is not None else None


def default_bg() -> Rgb | None:
    colors = default_colors()
    return colors.bg if colors is not None else None


__all__ = [
    "Color",
    "DefaultColors",
    "RUST_MODULE",
    "StdoutColorLevel",
    "XTERM_COLORS",
    "best_color",
    "default_bg",
    "default_colors",
    "default_fg",
    "indexed_color",
    "requery_default_colors",
    "rgb_color",
    "set_default_colors_from_startup_probe",
    "stdout_color_level",
    "xterm_fixed_colors",
]
