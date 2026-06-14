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
from pathlib import Path
from typing import Any, Callable, Iterable

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="pets::frames",
    source="codex/codex-rs/tui/src/pets/frames.rs",
)

FrameSlicer = Callable[[Any, tuple[Path, ...]], None]


def prepare_png_frames(
    pet: Any,
    frame_dir: str | os.PathLike[str],
    *,
    slicer: FrameSlicer | None = None,
) -> list[Path]:
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
        return not_ported(RUST_MODULE, "prepare_png_frames image slicing")

    slicer(pet, expected)
    return list(expected)


def glob_frame_files(frame_dir: str | os.PathLike[str]) -> list[Path]:
    """Return direct child files matching Rust's ``frame_*.png`` cleanup glob."""

    directory = Path(frame_dir)
    if not directory.exists():
        return []
    paths: list[Path] = []
    for entry in directory.iterdir():
        name = entry.name
        if entry.is_file() and name.startswith("frame_") and name.endswith(".png"):
            paths.append(entry)
    return paths


def expected_frame_paths(pet: Any, frame_dir: str | os.PathLike[str]) -> list[Path]:
    """Expose Rust's expected path calculation for semantic tests."""

    directory = Path(frame_dir)
    return [directory / f"frame_{index:03}.png" for index in range(_pet_frame_count(pet))]


def frame_crop_plan(pet: Any) -> list[tuple[int, int, int, int, int]]:
    """Return ``(index, x, y, width, height)`` plans Rust passes to ``try_view``."""

    frame_count = _pet_frame_count(pet)
    _validate_grid_geometry(pet, frame_count)
    columns = _pet_int(pet, "columns")
    rows = _pet_int(pet, "rows")
    width = _pet_int(pet, "frame_width")
    height = _pet_int(pet, "frame_height")
    plans: list[tuple[int, int, int, int, int]] = []
    for row in range(rows):
        for column in range(columns):
            index = _checked_add(_checked_mul(row, columns, "pet frame index overflow"), column, "pet frame index overflow")
            if index >= frame_count:
                raise IndexError("pet frame index exceeds expected frame count")
            x = _checked_mul(column, width, "pet frame x offset overflow")
            y = _checked_mul(row, height, "pet frame y offset overflow")
            plans.append((index, x, y, width, height))
    return plans


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
    value = getattr(pet, name, None)
    if value is None:
        raise AttributeError(f"pet must expose {name}")
    return int(value)


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


__all__ = [
    "FrameSlicer",
    "RUST_MODULE",
    "expected_frame_paths",
    "frame_crop_plan",
    "glob_frame_files",
    "prepare_png_frames",
]
