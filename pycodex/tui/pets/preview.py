"""Shared preview-state model for the ``/pets`` side pane.

Upstream source: ``codex/codex-rs/tui/src/pets/preview.rs``.

The Rust module wraps mutex-backed state and renders ratatui paragraphs.  Python
keeps the same state transitions and exposes a semantic render plan instead of
copying ratatui types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import threading
from typing import Any, Mapping, Sequence

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="pets::preview",
    source="codex/codex-rs/tui/src/pets/preview.rs",
)

RectTuple = tuple[int, int, int, int]


class PetPickerPreviewStatus(Enum):
    Hidden = "hidden"
    Loading = "loading"
    Disabled = "disabled"
    Ready = "ready"
    Error = "error"


@dataclass
class PetPickerPreviewInner:
    status: PetPickerPreviewStatus = PetPickerPreviewStatus.Hidden
    last_area: RectTuple | None = None
    message: str | None = None


@dataclass(frozen=True)
class PreviewLine:
    text: str
    style: str


@dataclass(frozen=True)
class PreviewRenderPlan:
    area: RectTuple
    text_area: RectTuple
    lines: tuple[PreviewLine, ...]
    alignment: str = "center"


@dataclass
class PetPickerPreviewState:
    _inner: PetPickerPreviewInner = field(default_factory=PetPickerPreviewInner)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def renderable(self) -> "PetPickerPreviewRenderable":
        return PetPickerPreviewRenderable(self)

    def set_loading(self) -> None:
        self.update(lambda inner: _set_status(inner, PetPickerPreviewStatus.Loading))

    def set_disabled(self) -> None:
        self.update(lambda inner: _set_status(inner, PetPickerPreviewStatus.Disabled))

    def set_ready(self) -> None:
        self.update(lambda inner: _set_status(inner, PetPickerPreviewStatus.Ready))

    def set_error(self, message: str) -> None:
        self.update(lambda inner: _set_status(inner, PetPickerPreviewStatus.Error, str(message)))

    def clear(self) -> None:
        def mutate(inner: PetPickerPreviewInner) -> None:
            inner.status = PetPickerPreviewStatus.Hidden
            inner.last_area = None
            inner.message = None

        self.update(mutate)

    def area(self) -> RectTuple | None:
        with self._lock:
            return self._inner.last_area

    def update(self, func: Any) -> None:
        with self._lock:
            func(self._inner)

    @property
    def status(self) -> PetPickerPreviewStatus:
        with self._lock:
            return self._inner.status


@dataclass
class PetPickerPreviewRenderable:
    state: PetPickerPreviewState

    def render(self, area: Any, buf: Any = None) -> PreviewRenderPlan | None:
        rect = _rect(area)
        with self.state._lock:
            self.state._inner.last_area = rect
            status = self.state._inner.status
            message = self.state._inner.message

        if status is PetPickerPreviewStatus.Hidden:
            return None
        if status is PetPickerPreviewStatus.Ready:
            return None
        if status is PetPickerPreviewStatus.Loading:
            title = "Loading preview..."
            body = None
        elif status is PetPickerPreviewStatus.Disabled:
            title = "Terminal pets disabled"
            body = "No pet will be shown."
        elif status is PetPickerPreviewStatus.Error:
            title = "Preview unavailable"
            body = message or ""
        else:
            return None

        text_height = 2 if body is not None else 1
        text_area = centered_text_area(rect, text_height)
        lines = [PreviewLine(title, "bold")]
        if body is not None:
            lines.append(PreviewLine(body, "dim"))
        return PreviewRenderPlan(area=rect, text_area=text_area, lines=tuple(lines))

    def desired_height(self, width: int) -> int:
        return 4


def centered_text_area(area: Any, height: int) -> RectTuple:
    x, y, width, area_height = _rect(area)
    text_height = min(int(height), area_height)
    text_y = y + max(0, area_height - text_height) // 2
    return (x, text_y, width, text_height)


def render(renderable: PetPickerPreviewRenderable, area: Any, buf: Any = None) -> PreviewRenderPlan | None:
    return renderable.render(area, buf)


def desired_height(renderable: PetPickerPreviewRenderable, width: int) -> int:
    return renderable.desired_height(width)


def _set_status(inner: PetPickerPreviewInner, status: PetPickerPreviewStatus, message: str | None = None) -> None:
    inner.status = status
    inner.message = message


def _rect(area: Any) -> RectTuple:
    if isinstance(area, Mapping):
        return (int(area["x"]), int(area["y"]), int(area["width"]), int(area["height"]))
    if isinstance(area, Sequence) and not isinstance(area, (str, bytes)):
        if len(area) != 4:
            raise ValueError("area sequence must contain x, y, width, height")
        return (int(area[0]), int(area[1]), int(area[2]), int(area[3]))
    return (int(area.x), int(area.y), int(area.width), int(area.height))


__all__ = [
    "PetPickerPreviewInner",
    "PetPickerPreviewRenderable",
    "PetPickerPreviewState",
    "PetPickerPreviewStatus",
    "PreviewLine",
    "PreviewRenderPlan",
    "RUST_MODULE",
    "centered_text_area",
    "desired_height",
    "render",
]
