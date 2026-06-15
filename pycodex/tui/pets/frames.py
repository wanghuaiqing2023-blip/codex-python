"""Pet spritesheet frame preparation.

Upstream source: ``codex/codex-rs/tui/src/pets/frames.rs``.

Rust slices a spritesheet into per-frame PNG files using the ``image`` crate.
This Python port preserves the module-owned filesystem behavior: expected frame
path generation, cache completeness detection, stale frame cleanup, and checked
row/column geometry.  Actual image decoding/slicing is an explicit dependency
boundary and can be supplied by an injected slicer for tests or host runtimes.
"""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="pets::frames",
    source="codex/codex-rs/tui/src/pets/frames.rs",
    status="complete",
)

FrameSlicer = Callable[[Any, Tuple[Path, ...]], None]


def prepare_png_frames(
    pet: Any,
    frame_dir: Any,
    *,
    slicer: Optional[FrameSlicer] = None,
) -> List[Path]:
    """Prepare one PNG file per pet frame and return the expected paths.

    Mirrors Rust ``prepare_png_frames`` up to the image-processing boundary:
    create the output directory, compute ``frame_{index:03}.png`` paths, reuse a
    complete cache, remove stale ``frame_*.png`` files when incomplete, validate
    the frame grid, then ask an injected slicer to materialize PNG frames.
    """

    target_dir = Path(frame_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    frame_count = _pet_frame_count(pet)
    expected = tuple(target_dir / f"frame_{index:03}.png" for index in range(frame_count))
    if all(path.exists() for path in expected):
        return list(expected)

    for stale in glob_frame_files(target_dir):
        try:
            stale.unlink()
        except FileNotFoundError:
            pass

    _validate_grid_geometry(pet, frame_count)
    if slicer is None:
        slicer = slice_png_spritesheet

    slicer(pet, expected)
    return list(expected)


def glob_frame_files(frame_dir: Any) -> List[Path]:
    """Return direct child files matching Rust's ``frame_*.png`` cleanup glob."""

    directory = Path(frame_dir)
    if not directory.exists():
        return []
    paths: List[Path] = []
    for entry in directory.iterdir():
        name = entry.name
        if entry.is_file() and name.startswith("frame_") and name.endswith(".png"):
            paths.append(entry)
    return paths


def expected_frame_paths(pet: Any, frame_dir: Any) -> List[Path]:
    """Expose Rust's expected path calculation for semantic tests."""

    directory = Path(frame_dir)
    return [directory / f"frame_{index:03}.png" for index in range(_pet_frame_count(pet))]


def frame_crop_plan(pet: Any) -> List[Tuple[int, int, int, int, int]]:
    """Return ``(index, x, y, width, height)`` plans Rust passes to ``try_view``."""

    frame_count = _pet_frame_count(pet)
    _validate_grid_geometry(pet, frame_count)
    columns = _pet_int(pet, "columns")
    rows = _pet_int(pet, "rows")
    width = _pet_int(pet, "frame_width")
    height = _pet_int(pet, "frame_height")
    plans: List[Tuple[int, int, int, int, int]] = []
    for row in range(rows):
        for column in range(columns):
            index = _checked_add(_checked_mul(row, columns, "pet frame index overflow"), column, "pet frame index overflow")
            if index >= frame_count:
                raise IndexError("pet frame index exceeds expected frame count")
            x = _checked_mul(column, width, "pet frame x offset overflow")
            y = _checked_mul(row, height, "pet frame y offset overflow")
            plans.append((index, x, y, width, height))
    return plans


def slice_png_spritesheet(pet: Any, expected: Tuple[Path, ...]) -> None:
    image = _read_png_rgba8(Path(_pet_value(pet, "spritesheet_path")))
    image_width, image_height, pixels = image
    for index, x, y, width, height in frame_crop_plan(pet):
        if x + width > image_width or y + height > image_height:
            raise ValueError("pet frame crop exceeds spritesheet bounds")
        frame_rows = []
        for row in range(y, y + height):
            start = (row * image_width + x) * 4
            end = start + width * 4
            frame_rows.append(pixels[start:end])
        _write_png_rgba8(expected[index], width, height, b"".join(frame_rows))


def _validate_grid_geometry(pet: Any, frame_count: int) -> None:
    columns = _pet_int(pet, "columns")
    rows = _pet_int(pet, "rows")
    width = _pet_int(pet, "frame_width")
    height = _pet_int(pet, "frame_height")
    if columns < 0 or rows < 0 or width < 0 or height < 0 or frame_count < 0:
        raise ValueError("pet frame geometry must be non-negative")
    grid_count = _checked_mul(rows, columns, "pet frame index overflow")
    if grid_count > frame_count:
        raise IndexError("pet frame index exceeds expected frame count")


def _pet_frame_count(pet: Any) -> int:
    value = getattr(pet, "frame_count", None)
    if callable(value):
        return int(value())
    if value is not None:
        return int(value)
    value = getattr(pet, "frame_count_value", None)
    if value is not None:
        return int(value)
    raise AttributeError("pet must expose frame_count or frame_count_value")


def _pet_int(pet: Any, name: str) -> int:
    value = _pet_value(pet, name)
    if value is None:
        raise AttributeError(f"pet must expose {name}")
    return int(value)


def _pet_value(pet: Any, name: str) -> Any:
    if isinstance(pet, dict):
        return pet.get(name)
    return getattr(pet, name, None)


def _checked_mul(left: int, right: int, message: str) -> int:
    result = left * right
    if result > 0xFFFF_FFFF:
        raise OverflowError(message)
    return result


def _checked_add(left: int, right: int, message: str) -> int:
    result = left + right
    if result > 0xFFFF_FFFF:
        raise OverflowError(message)
    return result


def _read_png_rgba8(path: Path) -> Tuple[int, int, bytes]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("unsupported spritesheet format; expected PNG")
    pos = 8
    width = height = None
    color_type = bit_depth = None
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", payload[:10])
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    if width is None or height is None:
        raise ValueError("invalid PNG: missing IHDR")
    if bit_depth != 8 or color_type != 6:
        raise ValueError("unsupported PNG format; expected 8-bit RGBA")
    decompressed = zlib.decompress(bytes(idat))
    stride = width * 4
    rows = []
    prev = bytes(stride)
    cursor = 0
    for _row in range(height):
        filter_type = decompressed[cursor]
        cursor += 1
        raw = bytearray(decompressed[cursor : cursor + stride])
        cursor += stride
        if filter_type == 0:
            recon = raw
        elif filter_type == 1:
            recon = _png_unfilter_sub(raw, 4)
        elif filter_type == 2:
            recon = _png_unfilter_up(raw, prev)
        elif filter_type == 3:
            recon = _png_unfilter_average(raw, prev, 4)
        elif filter_type == 4:
            recon = _png_unfilter_paeth(raw, prev, 4)
        else:
            raise ValueError("invalid PNG filter")
        prev = bytes(recon)
        rows.append(prev)
    return width, height, b"".join(rows)


def _write_png_rgba8(path: Path, width: int, height: int, pixels: bytes) -> None:
    if len(pixels) != width * height * 4:
        raise ValueError("invalid RGBA buffer length")
    raw = bytearray()
    stride = width * 4
    for row in range(height):
        raw.append(0)
        raw.extend(pixels[row * stride : (row + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(_png_chunk(b"IHDR", ihdr))
    png.extend(_png_chunk(b"IDAT", zlib.compress(bytes(raw))))
    png.extend(_png_chunk(b"IEND", b""))
    path.write_bytes(bytes(png))


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind)
    crc = zlib.crc32(payload, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _png_unfilter_sub(raw: bytearray, bpp: int) -> bytearray:
    for i in range(bpp, len(raw)):
        raw[i] = (raw[i] + raw[i - bpp]) & 0xFF
    return raw


def _png_unfilter_up(raw: bytearray, prev: bytes) -> bytearray:
    for i in range(len(raw)):
        raw[i] = (raw[i] + prev[i]) & 0xFF
    return raw


def _png_unfilter_average(raw: bytearray, prev: bytes, bpp: int) -> bytearray:
    for i in range(len(raw)):
        left = raw[i - bpp] if i >= bpp else 0
        up = prev[i]
        raw[i] = (raw[i] + ((left + up) // 2)) & 0xFF
    return raw


def _png_unfilter_paeth(raw: bytearray, prev: bytes, bpp: int) -> bytearray:
    for i in range(len(raw)):
        left = raw[i - bpp] if i >= bpp else 0
        up = prev[i]
        up_left = prev[i - bpp] if i >= bpp else 0
        raw[i] = (raw[i] + _paeth(left, up, up_left)) & 0xFF
    return raw


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


__all__ = [
    "FrameSlicer",
    "RUST_MODULE",
    "expected_frame_paths",
    "frame_crop_plan",
    "glob_frame_files",
    "prepare_png_frames",
    "slice_png_spritesheet",
]
