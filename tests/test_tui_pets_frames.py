"""Parity tests for ``codex-tui/src/pets/frames.rs``."""

from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib

import pytest

from pycodex.tui.pets.frames import (
    expected_frame_paths,
    frame_crop_plan,
    glob_frame_files,
    prepare_png_frames,
)


@dataclass
class TinyPet:
    frame_width: int = 1
    frame_height: int = 1
    columns: int = 2
    rows: int = 1
    frame_count_value: int = 2

    def frame_count(self) -> int:
        return self.frame_count_value


def test_glob_frame_files_matches_only_direct_frame_png_children(tmp_path):
    (tmp_path / "frame_000.png").write_text("a", encoding="utf-8")
    (tmp_path / "frame_old.png").write_text("b", encoding="utf-8")
    (tmp_path / "frame_000.txt").write_text("c", encoding="utf-8")
    (tmp_path / "other.png").write_text("d", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "frame_999.png").write_text("e", encoding="utf-8")

    assert sorted(path.name for path in glob_frame_files(tmp_path)) == ["frame_000.png", "frame_old.png"]
    assert glob_frame_files(tmp_path / "missing") == []


def test_prepare_png_frames_reuses_complete_cache_without_slicer(tmp_path):
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    for path in expected_frame_paths(TinyPet(), frame_dir):
        path.write_text("cached", encoding="utf-8")

    assert prepare_png_frames(TinyPet(), frame_dir) == expected_frame_paths(TinyPet(), frame_dir)


def test_prepare_png_frames_removes_stale_files_and_uses_injected_slicer(tmp_path):
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    stale = frame_dir / "frame_stale.png"
    stale.write_text("stale", encoding="utf-8")
    keep = frame_dir / "not_a_frame.png"
    keep.write_text("keep", encoding="utf-8")
    calls = []

    def slicer(pet, expected):
        calls.append((pet, tuple(path.name for path in expected)))
        for index, path in enumerate(expected):
            path.write_text(f"frame {index}", encoding="utf-8")

    paths = prepare_png_frames(TinyPet(), frame_dir, slicer=slicer)

    assert [path.name for path in paths] == ["frame_000.png", "frame_001.png"]
    assert calls == [(TinyPet(), ("frame_000.png", "frame_001.png"))]
    assert not stale.exists()
    assert keep.exists()
    assert all(path.exists() for path in paths)


def test_frame_crop_plan_matches_rust_row_column_offsets():
    assert frame_crop_plan(TinyPet(frame_width=10, frame_height=20, columns=2, rows=2, frame_count_value=4)) == [
        (0, 0, 0, 10, 20),
        (1, 10, 0, 10, 20),
        (2, 0, 20, 10, 20),
        (3, 10, 20, 10, 20),
    ]


def test_prepare_png_frames_requires_explicit_image_slicing_boundary(tmp_path):
    spritesheet = tmp_path / "sheet.png"
    _write_png_rgba8(
        spritesheet,
        2,
        1,
        bytes(
            [
                255,
                0,
                0,
                255,
                0,
                255,
                0,
                255,
            ]
        ),
    )
    pet = TinyPet()
    pet.spritesheet_path = spritesheet

    frames = prepare_png_frames(pet, tmp_path / "frames")

    assert len(frames) == 2
    assert _read_png_rgba8(frames[0]) == (1, 1, bytes([255, 0, 0, 255]))
    assert _read_png_rgba8(frames[1]) == (1, 1, bytes([0, 255, 0, 255]))


def test_frame_crop_plan_rejects_grid_larger_than_frame_count():
    with pytest.raises(IndexError, match="pet frame index exceeds expected frame count"):
        frame_crop_plan(TinyPet(columns=2, rows=2, frame_count_value=3))


def test_prepare_png_frames_rejects_crop_outside_spritesheet(tmp_path):
    spritesheet = tmp_path / "small.png"
    _write_png_rgba8(spritesheet, 1, 1, bytes([0, 0, 0, 255]))
    pet = TinyPet(frame_width=2, frame_height=1, columns=1, rows=1, frame_count_value=1)
    pet.spritesheet_path = spritesheet

    with pytest.raises(ValueError, match="pet frame crop exceeds spritesheet bounds"):
        prepare_png_frames(pet, tmp_path / "frames")


def _write_png_rgba8(path, width, height, pixels):
    raw = bytearray()
    stride = width * 4
    for row in range(height):
        raw.append(0)
        raw.extend(pixels[row * stride : (row + 1) * stride])
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    png.extend(_chunk(b"IDAT", zlib.compress(bytes(raw))))
    png.extend(_chunk(b"IEND", b""))
    path.write_bytes(bytes(png))


def _read_png_rgba8(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    width = height = None
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height = struct.unpack(">II", payload[:8])
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    raw = zlib.decompress(bytes(idat))
    rows = []
    stride = width * 4
    cursor = 0
    for _ in range(height):
        assert raw[cursor] == 0
        cursor += 1
        rows.append(raw[cursor : cursor + stride])
        cursor += stride
    return width, height, b"".join(rows)


def _chunk(kind, payload):
    crc = zlib.crc32(kind)
    crc = zlib.crc32(payload, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)
