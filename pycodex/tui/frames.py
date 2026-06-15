"""Embedded animation frame sets for ``codex-tui::frames``.

Rust source: ``codex/codex-rs/tui/src/frames.rs`` embeds 36 text frames for
each animation variant with ``include_str!``.  Python preserves the same data
boundary by loading those authoritative frame files from the upstream checkout
at import time; missing frame files are treated as hard parity errors rather
than silently fabricating placeholder frames.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import List, Tuple

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="frames",
    source="codex/codex-rs/tui/src/frames.rs",
    status="complete",
)

_FRAME_COUNT = 36
_VARIANT_NAMES = (
    "default",
    "codex",
    "openai",
    "blocks",
    "dots",
    "hash",
    "hbars",
    "vbars",
    "shapes",
    "slug",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _frames_root() -> Path:
    return _repo_root() / "codex" / "codex-rs" / "tui" / "frames"


def _load_frames(variant: str) -> Tuple[str, ...]:
    variant_dir = _frames_root() / variant
    frames: List[str] = []
    for index in range(1, _FRAME_COUNT + 1):
        frame_path = variant_dir / f"frame_{index}.txt"
        frames.append(frame_path.read_text(encoding="utf-8"))
    return tuple(frames)


FRAMES_DEFAULT = _load_frames("default")
FRAMES_CODEX = _load_frames("codex")
FRAMES_OPENAI = _load_frames("openai")
FRAMES_BLOCKS = _load_frames("blocks")
FRAMES_DOTS = _load_frames("dots")
FRAMES_HASH = _load_frames("hash")
FRAMES_HBARS = _load_frames("hbars")
FRAMES_VBARS = _load_frames("vbars")
FRAMES_SHAPES = _load_frames("shapes")
FRAMES_SLUG = _load_frames("slug")

ALL_VARIANTS = (
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

FRAME_TICK_DEFAULT = timedelta(milliseconds=80)

__all__ = [
    "ALL_VARIANTS",
    "FRAMES_BLOCKS",
    "FRAMES_CODEX",
    "FRAMES_DEFAULT",
    "FRAMES_DOTS",
    "FRAMES_HASH",
    "FRAMES_HBARS",
    "FRAMES_OPENAI",
    "FRAMES_SHAPES",
    "FRAMES_SLUG",
    "FRAMES_VBARS",
    "FRAME_TICK_DEFAULT",
    "RUST_MODULE",
]
