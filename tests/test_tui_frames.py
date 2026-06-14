"""Parity tests for Rust ``codex-tui::frames``.

Rust source: ``codex/codex-rs/tui/src/frames.rs``.
"""

from datetime import timedelta
from pathlib import Path

from pycodex.tui.frames import (
    ALL_VARIANTS,
    FRAMES_BLOCKS,
    FRAMES_CODEX,
    FRAMES_DEFAULT,
    FRAMES_DOTS,
    FRAMES_HASH,
    FRAMES_HBARS,
    FRAMES_OPENAI,
    FRAMES_SHAPES,
    FRAMES_SLUG,
    FRAMES_VBARS,
    FRAME_TICK_DEFAULT,
)


def test_all_frame_variants_match_rust_shape() -> None:
    variants = (
        FRAMES_DEFAULT,
        FRAMES_CODEX,
        FRAMES_OPENAI,
        FRAMES_BLOCKS,
        FRAMES_DOTS,
        FRAMES_HASH,
        FRAMES_HBARS,
        FRAMES_VBARS,
        FRAMES_SHAPES,
        FRAMES_SLUG,
    )
    assert ALL_VARIANTS == variants
    assert len(ALL_VARIANTS) == 10
    assert all(len(variant) == 36 for variant in ALL_VARIANTS)
    assert all(isinstance(frame, str) and frame for variant in ALL_VARIANTS for frame in variant)


def test_frame_tick_default_is_80ms() -> None:
    assert FRAME_TICK_DEFAULT == timedelta(milliseconds=80)


def test_frame_sets_load_authoritative_upstream_files() -> None:
    # Rust: frames_for! includes frame_1.txt through frame_36.txt for each variant.
    frames_root = Path(__file__).resolve().parents[1] / "codex" / "codex-rs" / "tui" / "frames"

    assert FRAMES_DEFAULT[0] == (frames_root / "default" / "frame_1.txt").read_text(encoding="utf-8")
    assert FRAMES_SLUG[-1] == (frames_root / "slug" / "frame_36.txt").read_text(encoding="utf-8")
