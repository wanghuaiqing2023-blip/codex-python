"""Minimal Sixel encoder for pet sprites.

Upstream source: ``codex/codex-rs/tui/src/pets/sixel.rs``.

This intentionally mirrors Rust's narrow encoder, not a general-purpose Sixel
implementation. Input frames are RGBA bytes, colors are reduced with RGB332,
and transparent pixels are omitted from color planes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="pets::sixel",
    source="codex/codex-rs/tui/src/pets/sixel.rs",
)

ST = b"\x1b\\"
SIXEL_BAND_HEIGHT = 6
PALETTE_COLOR_COUNT = 256
TRANSPARENT_ALPHA_THRESHOLD = 128
TRANSPARENT_BACKGROUND_DCS = b"\x1bP9;1;0q"
EXPECTED_TRANSPARENT_BACKGROUND_DCS = "\x1bP9;1;0q"


def encode_rgba(rgba: bytes | bytearray | memoryview, width: int, height: int) -> bytes:
    rgba = bytes(rgba)
    if width == 0 or height == 0:
        raise ValueError("sixel image dimensions must be non-zero")

    expected_len = pixel_count(width, height) * 4
    if len(rgba) != expected_len:
        raise ValueError(f"sixel RGBA buffer has {len(rgba)} bytes, expected {expected_len}")

    palette = Palette.from_rgba(rgba)
    output = bytearray()
    output.extend(TRANSPARENT_BACKGROUND_DCS)
    output.extend(f'"1;1;{width};{height}'.encode())
    palette.write_definitions(output)
    write_pixels(output, rgba, width, height, palette)
    output.extend(ST)
    return bytes(output)


def write_pixels(
    output: bytearray,
    rgba: bytes,
    width: int,
    height: int,
    palette: "Palette",
) -> None:
    band_count = (height + SIXEL_BAND_HEIGHT - 1) // SIXEL_BAND_HEIGHT
    for band_index in range(band_count):
        band_top = band_index * SIXEL_BAND_HEIGHT
        colors = active_colors_for_band(rgba, width, height, band_top, palette)
        for position, color_index in enumerate(colors):
            output.extend(f"#{color_index}".encode())
            run_char: int | None = None
            run_len = 0
            for x in range(width):
                data = sixel_data_for_column(rgba, width, height, band_top, x, color_index)
                run_char, run_len = push_run(run_char, run_len, output, data)
            flush_run(run_char, run_len, output)
            if position + 1 < len(colors):
                output.append(ord("$"))

        if band_index + 1 < band_count:
            output.extend(b"-" if not colors else b"$-")


def active_colors_for_band(
    rgba: bytes,
    width: int,
    height: int,
    band_top: int,
    palette: "Palette",
) -> list[int]:
    active = [False] * PALETTE_COLOR_COUNT
    for y in range(band_top, min(height, band_top + SIXEL_BAND_HEIGHT)):
        for x in range(width):
            color_index = color_index_at(rgba, width, x, y)
            if color_index is not None:
                active[color_index] = True
    return [color_index for color_index in palette.indices() if active[color_index]]


def sixel_data_for_column(
    rgba: bytes,
    width: int,
    height: int,
    band_top: int,
    x: int,
    color_index: int,
) -> int:
    mask = 0
    for bit in range(SIXEL_BAND_HEIGHT):
        y = band_top + bit
        if y >= height:
            continue
        if color_index_at(rgba, width, x, y) == color_index:
            mask |= 1 << bit
    return ord("?") + mask


def color_index_at(rgba: bytes, width: int, x: int, y: int) -> int | None:
    offset = pixel_offset(width, x, y)
    alpha = rgba[offset + 3]
    if alpha < TRANSPARENT_ALPHA_THRESHOLD:
        return None
    return rgb332_index(rgba[offset], rgba[offset + 1], rgba[offset + 2])


def push_run(
    run_char: int | None,
    run_len: int,
    output: bytearray,
    byte: int,
) -> tuple[int | None, int]:
    if run_char == byte:
        return run_char, run_len + 1
    flush_run(run_char, run_len, output)
    return byte, 1


def flush_run(run_char: int | None, run_len: int, output: bytearray) -> None:
    if run_char is None:
        return
    if run_len > 3:
        output.extend(f"!{run_len}".encode())
        output.append(run_char)
    else:
        output.extend(bytes([run_char]) * run_len)


def pixel_offset(width: int, x: int, y: int) -> int:
    return ((y * width) + x) * 4


def pixel_count(width: int, height: int) -> int:
    return width * height


def rgb332_index(red: int, green: int, blue: int) -> int:
    red_bucket = red >> 5
    green_bucket = green >> 5
    blue_bucket = blue >> 6
    return (red_bucket << 5) | (green_bucket << 2) | blue_bucket


def rgb332_color(index: int) -> tuple[int, int, int]:
    red = index >> 5
    green = (index >> 2) & 0b111
    blue = index & 0b11
    return (
        scale_bucket_to_byte(red, 7),
        scale_bucket_to_byte(green, 7),
        scale_bucket_to_byte(blue, 3),
    )


def scale_bucket_to_byte(bucket: int, max_: int) -> int:
    return min(255, (bucket * 255) // max_)


def byte_to_sixel_percent(value: int) -> int:
    return min(100, (value * 100) // 255)


@dataclass(frozen=True)
class Palette:
    used: tuple[bool, ...]

    @classmethod
    def from_rgba(cls, rgba: bytes | bytearray | memoryview) -> "Palette":
        used = [False] * PALETTE_COLOR_COUNT
        data = bytes(rgba)
        for offset in range(0, len(data) - (len(data) % 4), 4):
            if data[offset + 3] < TRANSPARENT_ALPHA_THRESHOLD:
                continue
            used[rgb332_index(data[offset], data[offset + 1], data[offset + 2])] = True
        return cls(tuple(used))

    def indices(self) -> list[int]:
        return [index for index, is_used in enumerate(self.used) if is_used]

    def write_definitions(self, output: bytearray) -> None:
        for color_index in self.indices():
            red, green, blue = rgb332_color(color_index)
            output.extend(
                (
                    f"#{color_index};2;"
                    f"{byte_to_sixel_percent(red)};"
                    f"{byte_to_sixel_percent(green)};"
                    f"{byte_to_sixel_percent(blue)}"
                ).encode()
            )


__all__ = [
    "EXPECTED_TRANSPARENT_BACKGROUND_DCS",
    "PALETTE_COLOR_COUNT",
    "Palette",
    "RUST_MODULE",
    "SIXEL_BAND_HEIGHT",
    "ST",
    "TRANSPARENT_ALPHA_THRESHOLD",
    "TRANSPARENT_BACKGROUND_DCS",
    "active_colors_for_band",
    "byte_to_sixel_percent",
    "color_index_at",
    "encode_rgba",
    "flush_run",
    "pixel_count",
    "pixel_offset",
    "push_run",
    "rgb332_color",
    "rgb332_index",
    "scale_bucket_to_byte",
    "sixel_data_for_column",
    "write_pixels",
]
