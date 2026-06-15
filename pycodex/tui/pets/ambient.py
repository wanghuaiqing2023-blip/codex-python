"""Ambient terminal rendering semantics for the Codex companion.

Upstream source: ``codex/codex-rs/tui/src/pets/ambient.rs``.

This module ports the pure ambient-pet behavior: notification vocabulary and
lifetimes, animation frame timing, image size/layout calculations, frame path
selection, and semantic draw-request construction.  Real terminal image
protocol probing and frame-cache loading remain runtime boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import time
from typing import Any, List, Mapping, Optional, Sequence, Tuple, Union

from .._porting import RustTuiModule
from . import frames as frame_cache
from .image_protocol import ProtocolSelection
from .model import Animation, AnimationFrame, Pet

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="pets::ambient",
    source="codex/codex-rs/tui/src/pets/ambient.rs",
    status="complete",
)

PET_TARGET_HEIGHT_PX = 75
PET_COMPOSER_GAP_PX = 10
TERMINAL_ROW_HEIGHT_PX = 15

RUNNING_LIFETIME = 3 * 60
FAILED_LIFETIME = 60 * 60
WAITING_LIFETIME = 24 * 60 * 60
REVIEW_LIFETIME = 7 * 24 * 60 * 60


class PetNotificationKind(Enum):
    Running = "running"
    Waiting = "waiting"
    Review = "review"
    Failed = "failed"

    def animation_name(self) -> str:
        return {
            PetNotificationKind.Running: "running",
            PetNotificationKind.Waiting: "waiting",
            PetNotificationKind.Review: "review",
            PetNotificationKind.Failed: "failed",
        }[self]

    def label(self) -> str:
        return {
            PetNotificationKind.Running: "Running",
            PetNotificationKind.Waiting: "Needs input",
            PetNotificationKind.Review: "Ready",
            PetNotificationKind.Failed: "Blocked",
        }[self]

    def fallback_body(self) -> str:
        return {
            PetNotificationKind.Running: "Thinking",
            PetNotificationKind.Waiting: "Needs input",
            PetNotificationKind.Review: "Ready",
            PetNotificationKind.Failed: "Blocked",
        }[self]

    def lifetime(self) -> int:
        return {
            PetNotificationKind.Running: RUNNING_LIFETIME,
            PetNotificationKind.Waiting: WAITING_LIFETIME,
            PetNotificationKind.Review: REVIEW_LIFETIME,
            PetNotificationKind.Failed: FAILED_LIFETIME,
        }[self]


@dataclass(frozen=True)
class PetNotification:
    kind: PetNotificationKind
    body: str
    updated_at: float

    @classmethod
    def new(
        cls,
        kind: PetNotificationKind,
        body: Optional[str] = None,
        *,
        now: Optional[float] = None,
    ) -> "PetNotification":
        return cls(kind=kind, body=body if body is not None else kind.fallback_body(), updated_at=_now(now))

    def is_expired(self, now: Optional[float] = None) -> bool:
        return max(0.0, _now(now) - self.updated_at) >= self.kind.lifetime()


@dataclass(frozen=True)
class AmbientPetDraw:
    frame: Path
    protocol: str
    x: int
    y: int
    clear_top_y: int
    columns: int
    rows: int
    height_px: int
    sixel_dir: Path


@dataclass(frozen=True)
class ImageSize:
    columns: int
    rows: int
    height_px: int


@dataclass(frozen=True)
class AnimationFrameTick:
    sprite_index: int
    delay: Optional[float]


@dataclass
class AmbientPet:
    pet: Pet
    support: Any
    frames: List[Path]
    sixel_dir: Path
    frame_requester: Any = None
    notification: Optional[PetNotification] = None
    animation_started_at: float = field(default_factory=time.monotonic)
    animations_enabled: bool = True

    @classmethod
    def load(
        cls,
        selected_pet: Optional[str],
        codex_home: Union[str, Path],
        frame_requester: Any,
        animations_enabled: bool,
        *,
        now: Optional[float] = None,
        support: Any = None,
        frame_preparer: Any = None,
    ) -> "AmbientPet":
        home = Path(codex_home)
        pet = Pet.load_with_codex_home(selected_pet or "codex", home)
        cache_dir = (
            home
            / "cache"
            / "tui-pets"
            / "frame-cache"
            / pet.id
            / pet.frame_cache_key()
        )
        frame_dir = cache_dir / "frames"
        sixel_dir = cache_dir / "sixel"
        preparer = frame_cache.prepare_png_frames if frame_preparer is None else frame_preparer
        frames = [Path(path) for path in preparer(pet, frame_dir)]
        return cls(
            pet=pet,
            support=default_image_support() if support is None else support,
            frames=frames,
            sixel_dir=sixel_dir,
            frame_requester=frame_requester,
            notification=None,
            animation_started_at=_now(now),
            animations_enabled=animations_enabled,
        )

    def set_notification(
        self,
        kind: PetNotificationKind,
        body: Optional[str] = None,
        *,
        now: Optional[float] = None,
    ) -> None:
        timestamp = _now(now)
        self.notification = PetNotification.new(kind, body, now=timestamp)
        self.animation_started_at = timestamp

    def image_enabled(self) -> bool:
        return self._protocol() is not None

    def image_columns(self) -> int:
        return self.image_size().columns

    def set_image_support_for_tests(self, support: Any) -> None:
        self.support = support

    def schedule_next_frame(self) -> None:
        delay = self.next_frame_delay()
        if delay is not None and self.frame_requester is not None:
            scheduler = getattr(self.frame_requester, "schedule_frame_in", None)
            if scheduler is not None:
                scheduler(delay)

    def next_frame_delay(self, *, now: Optional[float] = None) -> Optional[float]:
        if self._protocol() is None or not self.animations_enabled:
            return None
        animation = self.current_animation(now=now)
        if animation is None:
            return None
        tick = current_animation_frame(animation, max(0.0, _now(now) - self.animation_started_at))
        return None if tick is None else tick.delay

    def draw_request(
        self,
        area: Any,
        composer_bottom_y: int,
        *,
        now: Optional[float] = None,
    ) -> Optional[AmbientPetDraw]:
        protocol = self._protocol()
        if protocol is None:
            return None
        rect = _rect(area)
        size = self.image_size()
        notification = self.visible_notification(now=now)
        required_height = size.rows + (notification_height(notification) if notification is not None else 0)
        sprite_bottom_y = max(0, int(composer_bottom_y) - composer_gap_rows())
        if sprite_bottom_y < rect[1] + required_height or rect[2] < size.columns:
            return None
        x = rect[0] + max(0, rect[2] - size.columns)
        y = max(0, sprite_bottom_y - size.rows)
        frame = self.current_frame_path(now=now)
        if frame is None:
            return None
        return AmbientPetDraw(
            frame=frame,
            protocol=protocol,
            x=x,
            y=y,
            clear_top_y=rect[1],
            columns=size.columns,
            rows=size.rows,
            height_px=size.height_px,
            sixel_dir=self.sixel_dir,
        )

    def preview_draw_request(self, area: Any) -> Optional[AmbientPetDraw]:
        protocol = self._protocol()
        if protocol is None:
            return None
        rect = _rect(area)
        size = self.image_size()
        if rect[2] < size.columns or rect[3] < size.rows:
            return None
        y = rect[1] + max(0, rect[3] - size.rows) // 2
        frame = self.first_idle_frame_path()
        if frame is None:
            return None
        return AmbientPetDraw(
            frame=frame,
            protocol=protocol,
            x=rect[0] + max(0, rect[2] - size.columns) // 2,
            y=y,
            clear_top_y=y,
            columns=size.columns,
            rows=size.rows,
            height_px=size.height_px,
            sixel_dir=self.sixel_dir,
        )

    def visible_notification(self, *, now: Optional[float] = None) -> Optional[PetNotification]:
        if self.notification is None or self.notification.is_expired(now):
            return None
        return self.notification

    def current_animation(self, *, now: Optional[float] = None) -> Optional[Animation]:
        notification = self.visible_notification(now=now)
        animation_name = "idle" if notification is None else notification.kind.animation_name()
        animation = self.pet.animations.get(animation_name) or self.pet.animations.get("idle")
        if animation is None:
            return None
        if animation.loop_start is None:
            elapsed = max(0.0, _now(now) - self.animation_started_at)
            if elapsed >= animation.total_duration():
                fallback = self.pet.animations.get(animation.fallback)
                if fallback is not None:
                    return fallback
        return animation

    def current_frame_path(self, *, now: Optional[float] = None) -> Optional[Path]:
        animation = self.current_animation(now=now)
        if animation is None:
            sprite_index = 0
        elif self.animations_enabled:
            tick = current_animation_frame(animation, max(0.0, _now(now) - self.animation_started_at))
            sprite_index = 0 if tick is None else tick.sprite_index
        else:
            sprite_index = animation.frames[0].sprite_index if animation.frames else 0
        return self.frame_path_for_sprite_index(sprite_index)

    def first_idle_frame_path(self) -> Optional[Path]:
        idle = self.pet.animations.get("idle")
        sprite_index = 0 if idle is None or not idle.frames else idle.frames[0].sprite_index
        return self.frame_path_for_sprite_index(sprite_index)

    def frame_path_for_sprite_index(self, sprite_index: int) -> Optional[Path]:
        if not self.frames:
            return None
        index = min(int(sprite_index), len(self.frames) - 1)
        return self.frames[index]

    def image_size(self) -> ImageSize:
        rows = max(1, round(PET_TARGET_HEIGHT_PX / TERMINAL_ROW_HEIGHT_PX))
        aspect = (self.pet.frame_height / self.pet.frame_width) * 0.52
        columns = max(1, round(rows / aspect))
        return ImageSize(columns=columns, rows=rows, height_px=PET_TARGET_HEIGHT_PX)

    def _protocol(self) -> Optional[str]:
        support = self.support
        if support is None:
            return None
        if isinstance(support, str):
            return support
        if isinstance(support, Mapping):
            value = support.get("protocol")
            return None if value is None else str(value)
        protocol = getattr(support, "protocol", None)
        if callable(protocol):
            value = protocol()
            return None if value is None else str(value)
        if protocol is not None:
            return str(protocol)
        return None


def composer_gap_rows() -> int:
    return max(1, round(PET_COMPOSER_GAP_PX / TERMINAL_ROW_HEIGHT_PX))


def default_image_support() -> Any:
    return ProtocolSelection.AUTO.resolve()


def current_animation_frame(animation: Animation, elapsed: float) -> Optional[AnimationFrameTick]:
    if len(animation.frames) <= 1:
        if not animation.frames:
            return None
        return AnimationFrameTick(sprite_index=animation.frames[0].sprite_index, delay=None)

    elapsed_seconds = max(0.0, elapsed)
    if animation.loop_start is not None and animation.loop_start < len(animation.frames):
        total = animation.total_duration()
        prefix = sum(frame.duration for frame in animation.frames[: animation.loop_start])
        loop = sum(frame.duration for frame in animation.frames[animation.loop_start :])
        if elapsed_seconds >= total and loop > 0:
            effective = prefix + ((elapsed_seconds - prefix) % loop)
        else:
            effective = elapsed_seconds
        return frame_at_elapsed(animation, effective)

    if elapsed_seconds >= animation.total_duration():
        return AnimationFrameTick(sprite_index=animation.frames[-1].sprite_index, delay=None)
    return frame_at_elapsed(animation, elapsed_seconds)


def frame_at_elapsed(animation: Animation, elapsed: float) -> Optional[AnimationFrameTick]:
    remaining = max(0.0, elapsed)
    for frame in animation.frames:
        frame_seconds = max(float(frame.duration), 1e-9)
        if remaining < frame_seconds:
            return AnimationFrameTick(sprite_index=frame.sprite_index, delay=frame_seconds - remaining)
        remaining = max(0.0, remaining - frame_seconds)
    if not animation.frames:
        return None
    return AnimationFrameTick(sprite_index=animation.frames[-1].sprite_index, delay=None)


def nanos_to_duration(nanos: int) -> float:
    return min(int(nanos), (1 << 64) - 1) / 1_000_000_000


def notification_height(notification: PetNotification) -> int:
    return 1 if notification.body == notification.kind.label() else 2


def test_animation() -> Animation:
    return Animation(
        frames=(AnimationFrame(0, 0.010), AnimationFrame(1, 0.010)),
        loop_start=0,
        fallback="idle",
    )


def test_ambient_pet(*, frame_requester: Any = None, animations_enabled: bool = True) -> AmbientPet:
    pet = Pet(
        id="test",
        display_name="Test",
        description="",
        spritesheet_path=Path("spritesheet.webp"),
        frame_width=192,
        frame_height=208,
        columns=8,
        rows=9,
        frame_count_value=72,
        animations={"idle": test_animation()},
    )
    return AmbientPet(
        pet=pet,
        support="Kitty",
        frames=[Path("frame-0.png"), Path("frame-1.png")],
        sixel_dir=Path(),
        frame_requester=frame_requester,
        animation_started_at=time.monotonic() - 0.015,
        animations_enabled=animations_enabled,
    )


def _now(now: Optional[float]) -> float:
    return time.monotonic() if now is None else float(now)


def _rect(area: Any) -> Tuple[int, int, int, int]:
    if isinstance(area, Mapping):
        return (int(area["x"]), int(area["y"]), int(area["width"]), int(area["height"]))
    if isinstance(area, Sequence) and not isinstance(area, (str, bytes)):
        if len(area) != 4:
            raise ValueError("area sequence must contain x, y, width, height")
        return tuple(int(value) for value in area)  # type: ignore[return-value]
    return (int(area.x), int(area.y), int(area.width), int(area.height))


__all__ = [
    "AmbientPet",
    "AmbientPetDraw",
    "AnimationFrameTick",
    "FAILED_LIFETIME",
    "ImageSize",
    "PET_COMPOSER_GAP_PX",
    "PET_TARGET_HEIGHT_PX",
    "PetNotification",
    "PetNotificationKind",
    "REVIEW_LIFETIME",
    "RUNNING_LIFETIME",
    "RUST_MODULE",
    "TERMINAL_ROW_HEIGHT_PX",
    "WAITING_LIFETIME",
    "composer_gap_rows",
    "current_animation_frame",
    "default_image_support",
    "frame_at_elapsed",
    "nanos_to_duration",
    "notification_height",
    "test_ambient_pet",
    "test_animation",
]
