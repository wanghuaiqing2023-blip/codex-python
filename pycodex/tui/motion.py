"""Centralized motion primitives for ``codex-tui::motion``.

Rust source: ``codex/codex-rs/tui/src/motion.rs``.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
import re
import time
from typing import List, Optional, Union

from ._porting import RustTuiModule
from .line_truncation import Span

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="motion",
    source="codex/codex-rs/tui/src/motion.rs",
)

_ACTIVITY_BULLET = "•"
_ACTIVITY_DIM = "◦"


class MotionMode(Enum):
    Animated = "animated"
    Reduced = "reduced"

    @classmethod
    def from_animations_enabled(cls, animations_enabled: bool) -> "MotionMode":
        return cls.Animated if animations_enabled else cls.Reduced


class ReducedMotionIndicator(Enum):
    Hidden = "hidden"
    StaticBullet = "static_bullet"


def activity_indicator(
    start_time: Optional[float],
    motion_mode: MotionMode,
    reduced_motion_indicator: ReducedMotionIndicator,
) -> Optional[Span]:
    if motion_mode is MotionMode.Animated:
        return animated_activity_indicator(start_time)
    if reduced_motion_indicator is ReducedMotionIndicator.Hidden:
        return None
    return Span(_ACTIVITY_BULLET, style="dim")


def shimmer_text(text: str, motion_mode: MotionMode) -> List[Span]:
    if motion_mode is MotionMode.Animated:
        return shimmer_spans(text)
    if text == "":
        return []
    return [Span(text)]


def supports_truecolor_stdout() -> bool:
    """Semantic boundary for Rust ``supports_color::on_cached(Stream::Stdout)``."""

    return False


def animated_activity_indicator(start_time: Optional[float]) -> Span:
    if supports_truecolor_stdout():
        spans = shimmer_spans(_ACTIVITY_BULLET)
        return spans[0] if spans else Span(_ACTIVITY_BULLET)
    elapsed_ms = 0 if start_time is None else max(0, int((time.monotonic() - start_time) * 1000 + 1e-9))
    blink_on = ((elapsed_ms // 600) % 2) == 0
    return Span(_ACTIVITY_BULLET) if blink_on else Span(_ACTIVITY_DIM, style="dim")


def shimmer_spans(text: str) -> List[Span]:
    if text == "":
        return []
    return [Span(text, style="shimmer")]


def collect_rust_files(directory: Union[str, Path], files: Optional[List[Path]] = None) -> List[Path]:
    out = [] if files is None else files
    for path in Path(directory).iterdir():
        if path.is_dir():
            collect_rust_files(path, out)
        elif path.suffix == ".rs":
            out.append(path)
    return out


def animation_primitive_allowlisted_path(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return normalized in {"motion.rs", "shimmer.rs"}


def animation_primitives_are_only_used_by_motion_module(src_dir: Union[str, Path]) -> List[str]:
    direct_spinner = re.compile(r"(^|[^A-Za-z0-9_])spinner\s*\(")
    direct_shimmer = re.compile(r"(^|[^A-Za-z0-9_])shimmer_spans\s*\(")
    root = Path(src_dir)
    violations: List[str] = []
    for path in collect_rust_files(root):
        relative_path = path.relative_to(root).as_posix()
        if animation_primitive_allowlisted_path(relative_path):
            continue
        contents = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(contents.splitlines(), start=1):
            code = line.split("//", 1)[0]
            if direct_spinner.search(code):
                violations.append(
                    f"{relative_path}:{line_number} contains a direct `spinner(...)` call; use crate::motion instead"
                )
            if direct_shimmer.search(code):
                violations.append(
                    f"{relative_path}:{line_number} contains a direct `shimmer_spans(...)` call; use crate::motion instead"
                )
    return violations


__all__ = [
    "MotionMode",
    "RUST_MODULE",
    "ReducedMotionIndicator",
    "activity_indicator",
    "animated_activity_indicator",
    "animation_primitive_allowlisted_path",
    "animation_primitives_are_only_used_by_motion_module",
    "collect_rust_files",
    "shimmer_spans",
    "shimmer_text",
    "supports_truecolor_stdout",
]
