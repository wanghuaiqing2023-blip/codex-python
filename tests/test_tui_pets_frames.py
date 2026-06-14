"""Parity tests for ``codex-tui/src/pets/frames.rs``."""

from __future__ import annotations

from dataclasses import dataclass

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
    with pytest.raises(NotImplementedError, match="prepare_png_frames image slicing"):
        prepare_png_frames(TinyPet(), tmp_path / "frames")


def test_frame_crop_plan_rejects_grid_larger_than_frame_count():
    with pytest.raises(IndexError, match="pet frame index exceeds expected frame count"):
        frame_crop_plan(TinyPet(columns=2, rows=2, frame_count_value=3))
