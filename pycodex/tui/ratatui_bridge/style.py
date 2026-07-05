"""Small semantic equivalent of ratatui style values.

This bridge is intentionally narrower than ratatui. It captures the style
information Codex TUI modules need to preserve behavior and can convert to
vendored Rich styles at the rendering edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Iterable, Optional, Tuple, Union

Rgb = Tuple[int, int, int]


class Modifier(str, Enum):
    BOLD = "bold"
    DIM = "dim"
    ITALIC = "italic"
    UNDERLINED = "underlined"
    REVERSED = "reversed"
    CROSSED_OUT = "crossed_out"


@dataclass(frozen=True)
class Color:
    kind: str
    value: Optional[Union[str, Rgb, int]] = None

    @classmethod
    def named(cls, name: str) -> "Color":
        return cls("named", name)

    @classmethod
    def rgb(cls, red: int, green: int, blue: int) -> "Color":
        return cls("rgb", (_channel(red), _channel(green), _channel(blue)))

    @classmethod
    def indexed(cls, index: int) -> "Color":
        if index < 0 or index > 255:
            raise ValueError("indexed color must fit in 0..=255")
        return cls("indexed", index)

    @classmethod
    def reset(cls) -> "Color":
        return cls("reset", None)

    def rich_color(self) -> Optional[str]:
        if self.kind == "reset":
            return None
        if self.kind == "rgb":
            red, green, blue = self.value  # type: ignore[misc]
            return f"rgb({red},{green},{blue})"
        if self.kind == "indexed":
            return f"color({self.value})"
        return str(self.value)

Color.Reset = Color.reset()
Color.Rgb = Color.rgb
Color.Indexed = Color.indexed
Color.Black = Color.named("black")
Color.Red = Color.named("red")
Color.Green = Color.named("green")
Color.Yellow = Color.named("yellow")
Color.Blue = Color.named("blue")
Color.Magenta = Color.named("magenta")
Color.Cyan = Color.named("cyan")
Color.Gray = Color.named("gray")
Color.DarkGray = Color.named("dark_gray")
Color.LightRed = Color.named("light_red")
Color.LightGreen = Color.named("light_green")
Color.LightYellow = Color.named("light_yellow")
Color.LightBlue = Color.named("light_blue")
Color.LightMagenta = Color.named("light_magenta")
Color.LightCyan = Color.named("light_cyan")
Color.White = Color.named("white")
@dataclass(frozen=True)
class Style:
    fg: Optional[Color] = None
    bg: Optional[Color] = None
    modifiers: FrozenSet[Modifier] = field(default_factory=frozenset)

    @classmethod
    def default(cls) -> "Style":
        return cls()

    @classmethod
    def reset(cls) -> "Style":
        return cls(fg=Color.reset(), bg=Color.reset())

    def patch(self, other: "Style") -> "Style":
        return Style(
            fg=other.fg if other.fg is not None else self.fg,
            bg=other.bg if other.bg is not None else self.bg,
            modifiers=self.modifiers | other.modifiers,
        )

    def with_fg(self, color: Union[Color, str]) -> "Style":
        return Style(fg=_color(color), bg=self.bg, modifiers=self.modifiers)

    def with_bg(self, color: Union[Color, str]) -> "Style":
        return Style(fg=self.fg, bg=_color(color), modifiers=self.modifiers)

    def add_modifier(self, *modifiers: Union[Modifier, str]) -> "Style":
        return Style(fg=self.fg, bg=self.bg, modifiers=self.modifiers | _modifiers(modifiers))

    def bold(self) -> "Style":
        return self.add_modifier(Modifier.BOLD)

    def dim(self) -> "Style":
        return self.add_modifier(Modifier.DIM)

    def italic(self) -> "Style":
        return self.add_modifier(Modifier.ITALIC)

    def underlined(self) -> "Style":
        return self.add_modifier(Modifier.UNDERLINED)

    def reversed(self) -> "Style":
        return self.add_modifier(Modifier.REVERSED)

    def to_rich_style(self):
        from pycodex.tui.rich_compat import Style as RichStyle

        kwargs = {
            "color": self.fg.rich_color() if self.fg is not None else None,
            "bgcolor": self.bg.rich_color() if self.bg is not None else None,
            "bold": Modifier.BOLD in self.modifiers or None,
            "dim": Modifier.DIM in self.modifiers or None,
            "italic": Modifier.ITALIC in self.modifiers or None,
            "underline": Modifier.UNDERLINED in self.modifiers or None,
            "reverse": Modifier.REVERSED in self.modifiers or None,
            "strike": Modifier.CROSSED_OUT in self.modifiers or None,
        }
        return RichStyle(**kwargs)


def _channel(value: int) -> int:
    if not isinstance(value, int):
        raise TypeError("RGB channel must be an int")
    if value < 0 or value > 255:
        raise ValueError("RGB channel must fit in u8")
    return value


def _color(value: Union[Color, str]) -> Color:
    return value if isinstance(value, Color) else Color.named(value)


def _modifiers(values: Iterable[Union[Modifier, str]]) -> FrozenSet[Modifier]:
    result: set[Modifier] = set()
    for value in values:
        result.add(value if isinstance(value, Modifier) else Modifier(value))
    return frozenset(result)


__all__ = ["Color", "Modifier", "Rgb", "Style"]


