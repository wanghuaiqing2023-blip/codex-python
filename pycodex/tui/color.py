"""Color helpers for TUI rendering.

Upstream source: ``codex/codex-rs/tui/src/color.rs``.
"""

from __future__ import annotations

import math
from typing import Tuple

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="color",
    source="codex/codex-rs/tui/src/color.rs",
    status="complete",
)

Rgb = Tuple[int, int, int]


def _channel(value: int, name: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0 or value > 255:
        raise ValueError(f"{name} must fit in u8")
    return value


def _rgb(value: Rgb, name: str) -> Rgb:
    if len(value) != 3:
        raise ValueError(f"{name} must contain three RGB channels")
    return (
        _channel(value[0], f"{name}[0]"),
        _channel(value[1], f"{name}[1]"),
        _channel(value[2], f"{name}[2]"),
    )


def is_light(bg: Rgb) -> bool:
    """Return whether an RGB background is light.

    Mirrors Rust's luminance threshold:
    ``0.299*r + 0.587*g + 0.114*b > 128.0``.
    """

    r, g, b = _rgb(bg, "bg")
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return y > 128.0


def blend(fg: Rgb, bg: Rgb, alpha: float) -> Rgb:
    """Blend foreground and background RGB channels using Rust's truncation."""

    fr, fg_g, fb = _rgb(fg, "fg")
    br, bg_g, bb = _rgb(bg, "bg")
    return (
        int(fr * alpha + br * (1.0 - alpha)),
        int(fg_g * alpha + bg_g * (1.0 - alpha)),
        int(fb * alpha + bb * (1.0 - alpha)),
    )


def _srgb_to_linear(channel: int) -> float:
    c = channel / 255.0
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _rgb_to_xyz(r: int, g: int, b: int) -> Tuple[float, float, float]:
    rl = _srgb_to_linear(r)
    gl = _srgb_to_linear(g)
    bl = _srgb_to_linear(b)
    x = rl * 0.4124 + gl * 0.3576 + bl * 0.1805
    y = rl * 0.2126 + gl * 0.7152 + bl * 0.0722
    z = rl * 0.0193 + gl * 0.1192 + bl * 0.9505
    return (x, y, z)


def _lab_f(t: float) -> float:
    if t > 0.008856:
        return t ** (1.0 / 3.0)
    return 7.787 * t + 16.0 / 116.0


def _xyz_to_lab(x: float, y: float, z: float) -> Tuple[float, float, float]:
    xr = x / 0.95047
    yr = y / 1.00000
    zr = z / 1.08883
    fx = _lab_f(xr)
    fy = _lab_f(yr)
    fz = _lab_f(zr)
    lightness = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return (lightness, a, b)


def perceptual_distance(a: Rgb, b: Rgb) -> float:
    """Return CIE76-style Euclidean distance in Lab space approximation."""

    ar, ag, ab = _rgb(a, "a")
    br, bg, bb = _rgb(b, "b")
    x1, y1, z1 = _rgb_to_xyz(ar, ag, ab)
    x2, y2, z2 = _rgb_to_xyz(br, bg, bb)
    l1, a1, b1 = _xyz_to_lab(x1, y1, z1)
    l2, a2, b2 = _xyz_to_lab(x2, y2, z2)
    dl = l1 - l2
    da = a1 - a2
    db = b1 - b2
    return math.sqrt(dl * dl + da * da + db * db)


__all__ = [
    "RUST_MODULE",
    "Rgb",
    "blend",
    "is_light",
    "perceptual_distance",
]
