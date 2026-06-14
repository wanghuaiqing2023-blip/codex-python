"""Welcome step rendering for TUI onboarding.

Upstream source: ``codex/codex-rs/tui/src/onboarding/welcome.rs``.

Rust renders into ratatui and drives ``AsciiAnimation``.  Python keeps the same
state machine and exposes semantic render lines plus a small deterministic
animation model for parity tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="onboarding::welcome",
    source="codex/codex-rs/tui/src/onboarding/welcome.rs",
)

MIN_ANIMATION_HEIGHT = 37
MIN_ANIMATION_WIDTH = 60
WELCOME_LINE_PARTS = ("  ", "Welcome to ", "Codex", ", OpenAI's command-line coding agent")


class StepState(Enum):
    Hidden = "hidden"
    Complete = "complete"


@dataclass
class AsciiAnimationModel:
    variants: tuple[tuple[str, ...], ...] = (("frame-a",), ("frame-b",))
    variant_idx: int = 0
    scheduled_frames: int = 0

    def current_frame(self) -> tuple[str, ...]:
        return self.variants[self.variant_idx]

    def schedule_next_frame(self) -> None:
        self.scheduled_frames += 1

    def pick_random_variant(self) -> None:
        if len(self.variants) <= 1:
            return
        self.variant_idx = (self.variant_idx + 1) % len(self.variants)


@dataclass(frozen=True)
class WelcomeRenderPlan:
    area: tuple[int, int, int, int]
    cleared: bool
    show_animation: bool
    lines: tuple[str, ...]
    welcome_row: int
    wrap_trim: bool = False


@dataclass
class WelcomeWidget:
    is_logged_in: bool
    request_frame: Any = None
    animations_enabled: bool = True
    animation: AsciiAnimationModel = field(default_factory=AsciiAnimationModel)
    animations_suppressed: bool = False
    layout_area: tuple[int, int, int, int] | None = None

    @classmethod
    def new(cls, is_logged_in: bool, request_frame: Any = None, animations_enabled: bool = True) -> "WelcomeWidget":
        return cls(is_logged_in=is_logged_in, request_frame=request_frame, animations_enabled=animations_enabled)

    def update_layout_area(self, area: Any) -> None:
        self.layout_area = _rect(area)

    def set_animations_suppressed(self, suppressed: bool) -> None:
        self.animations_suppressed = bool(suppressed)

    def handle_key_event(self, key_event: Any) -> None:
        if not self.animations_enabled:
            return
        if _key_kind(key_event) == "press" and _is_toggle_animation_key(key_event):
            self.animation.pick_random_variant()

    def render_ref(self, area: Any, buf: Any = None) -> WelcomeRenderPlan:
        rect = _rect(area)
        if self.animations_enabled and not self.animations_suppressed:
            self.animation.schedule_next_frame()

        layout_area = self.layout_area or rect
        show_animation = (
            self.animations_enabled
            and not self.animations_suppressed
            and layout_area[3] >= MIN_ANIMATION_HEIGHT
            and layout_area[2] >= MIN_ANIMATION_WIDTH
        )
        lines: list[str] = []
        if show_animation:
            lines.extend(self.animation.current_frame())
            lines.append("")
        welcome_row = len(lines)
        lines.append("".join(WELCOME_LINE_PARTS))
        return WelcomeRenderPlan(
            area=rect,
            cleared=True,
            show_animation=show_animation,
            lines=tuple(lines),
            welcome_row=welcome_row,
        )

    def get_step_state(self) -> StepState:
        return StepState.Hidden if self.is_logged_in else StepState.Complete


def handle_key_event(widget: WelcomeWidget, key_event: Any) -> None:
    widget.handle_key_event(key_event)


def render_ref(widget: WelcomeWidget, area: Any, buf: Any = None) -> WelcomeRenderPlan:
    return widget.render_ref(area, buf)


def get_step_state(widget: WelcomeWidget) -> StepState:
    return widget.get_step_state()


def row_containing(lines: Sequence[str], needle: str) -> int | None:
    for index, line in enumerate(lines):
        if needle in line:
            return index
    return None


def _rect(area: Any) -> tuple[int, int, int, int]:
    if isinstance(area, Mapping):
        return (int(area["x"]), int(area["y"]), int(area["width"]), int(area["height"]))
    if isinstance(area, Sequence) and not isinstance(area, (str, bytes)):
        if len(area) != 4:
            raise ValueError("area sequence must contain x, y, width, height")
        return (int(area[0]), int(area[1]), int(area[2]), int(area[3]))
    return (int(area.x), int(area.y), int(area.width), int(area.height))


def _key_kind(key_event: Any) -> str:
    if isinstance(key_event, Mapping):
        return str(key_event.get("kind", "press")).lower()
    return str(getattr(key_event, "kind", "press")).lower()


def _is_toggle_animation_key(key_event: Any) -> bool:
    if isinstance(key_event, Mapping):
        char = key_event.get("char", key_event.get("code"))
        modifiers = key_event.get("modifiers", set())
    else:
        char = getattr(key_event, "char", getattr(key_event, "code", None))
        modifiers = getattr(key_event, "modifiers", set())
    if isinstance(modifiers, str):
        normalized = {part.strip().lower() for part in modifiers.replace("|", "+").split("+") if part.strip()}
    else:
        normalized = {str(part).lower() for part in modifiers}
    return char == "." and "control" in normalized


__all__ = [
    "AsciiAnimationModel",
    "MIN_ANIMATION_HEIGHT",
    "MIN_ANIMATION_WIDTH",
    "RUST_MODULE",
    "StepState",
    "WELCOME_LINE_PARTS",
    "WelcomeRenderPlan",
    "WelcomeWidget",
    "get_step_state",
    "handle_key_event",
    "render_ref",
    "row_containing",
]
