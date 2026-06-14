"""Ambient terminal pets configured from the ``/pets`` slash command.

Upstream source: ``codex/codex-rs/tui/src/pets/mod.rs``.

This package module owns the TUI-facing pet facade: default ids, built-in asset
ensure behavior, render-state bookkeeping, image clear behavior, and error
classification.  Python uses semantic ANSI output helpers instead of crossterm
queue macros, while preserving the observable escape-sequence order used by the
Rust tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, BinaryIO

from .._porting import RustTuiModule
from . import asset_pack, catalog, image_protocol
from .ambient import AmbientPet, AmbientPetDraw, PetNotificationKind, test_ambient_pet
from .image_protocol import ImageProtocol, PetImageSupport, PetImageUnsupportedReason
from .preview import PetPickerPreviewState
from .picker import PET_PICKER_VIEW_ID, build_pet_picker_params

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="pets",
    source="codex/codex-rs/tui/src/pets/mod.rs",
)

DEFAULT_PET_ID = "codex"
DISABLED_PET_ID = "disabled"
AMBIENT_PET_IMAGE_ID = 0xC0DE
PET_PICKER_PREVIEW_IMAGE_ID = 0xC0DF


class PetImageRenderError(Exception):
    kind: str

    def __init__(self, kind: str, error: BaseException):
        self.kind = kind
        self.error = error
        super().__init__(self.__str__())

    @classmethod
    def terminal(cls, error: BaseException) -> "PetImageRenderError":
        return cls("terminal", error)

    @classmethod
    def asset(cls, error: BaseException) -> "PetImageRenderError":
        return cls("asset", error)

    def __str__(self) -> str:
        if self.kind == "terminal":
            return f"terminal image write failed: {self.error}"
        return f"pet image asset unavailable: {self.error}"

    def source(self) -> BaseException:
        return self.error


@dataclass
class PetImageRenderState:
    last_sixel_clear_area: "SixelClearArea | None" = None
    last_protocol: ImageProtocol | None = None


class AmbientPetPayload(Enum):
    Text = "text"
    Bytes = "bytes"


@dataclass(frozen=True)
class SixelClearArea:
    x: int
    clear_top_y: int
    clear_bottom_y: int
    columns: int

    @classmethod
    def from_draw(cls, request: AmbientPetDraw) -> "SixelClearArea":
        return cls(
            x=request.x,
            clear_top_y=request.clear_top_y,
            clear_bottom_y=request.y + request.rows,
            columns=request.columns,
        )


def ensure_builtin_pack_for_pet(
    pet_id: str,
    codex_home: str | Path,
    *,
    ensure_fn: Callable[[str | Path, Any], None] | None = None,
) -> None:
    pet = catalog.builtin_pet(pet_id)
    if pet is not None:
        ensure = asset_pack.ensure_builtin_pet if ensure_fn is None else ensure_fn
        ensure(codex_home, pet)


def render_ambient_pet_image(writer: Any, state: PetImageRenderState, request: AmbientPetDraw | None) -> None:
    render_pet_image(writer, state, AMBIENT_PET_IMAGE_ID, request)


def render_pet_picker_preview_image(writer: Any, state: PetImageRenderState, request: AmbientPetDraw | None) -> None:
    render_pet_image(writer, state, PET_PICKER_PREVIEW_IMAGE_ID, request)


def render_pet_image(
    writer: Any,
    state: PetImageRenderState,
    image_id: int,
    request: AmbientPetDraw | None,
    *,
    sixel_frame_fn: Callable[[Path, Path, int], Path] | None = None,
) -> None:
    try:
        if request is None:
            previous_protocol = state.last_protocol
            state.last_protocol = None
            if previous_protocol is not None and is_kitty_protocol(previous_protocol):
                _write(writer, image_protocol.kitty_delete_image(image_id))
            if state.last_sixel_clear_area is not None:
                area = state.last_sixel_clear_area
                state.last_sixel_clear_area = None
                _write(writer, "\x1b7")
                clear_sixel_area(writer, area)
                _write(writer, "\x1b8")
            _flush(writer)
            return

        protocol = _coerce_protocol(request.protocol)
        previous_protocol = state.last_protocol
        if (previous_protocol is not None and is_kitty_protocol(previous_protocol)) or is_kitty_protocol(protocol):
            _write(writer, image_protocol.kitty_delete_image(image_id))
        state.last_protocol = protocol

        payload_kind, payload = _payload_for_request(request, protocol, image_id, sixel_frame_fn=sixel_frame_fn)
        _write(writer, "\x1b7")
        current_sixel_area = SixelClearArea.from_draw(request) if protocol is ImageProtocol.SIXEL else None
        previous_area = state.last_sixel_clear_area
        state.last_sixel_clear_area = None
        if previous_area is not None and previous_area != current_sixel_area:
            clear_sixel_area(writer, previous_area)
        if current_sixel_area is not None:
            clear_sixel_area(writer, current_sixel_area)
            state.last_sixel_clear_area = current_sixel_area
        _write(writer, _move_to(request.x, request.y))
        if payload_kind is AmbientPetPayload.Bytes:
            _write(writer, payload)
        else:
            _write(writer, str(payload))
        _write(writer, "\x1b8")
        _flush(writer)
    except PetImageRenderError:
        raise
    except OSError as exc:
        raise PetImageRenderError.terminal(exc) from exc


def is_kitty_protocol(protocol: ImageProtocol | str) -> bool:
    protocol = _coerce_protocol(protocol)
    return protocol in {ImageProtocol.KITTY, ImageProtocol.KITTY_LOCAL_FILE}


def clear_sixel_area(writer: Any, area: SixelClearArea) -> None:
    blank = " " * int(area.columns)
    for row in range(area.clear_top_y, area.clear_bottom_y):
        _write(writer, _move_to(area.x, row))
        _write(writer, blank)


def _payload_for_request(
    request: AmbientPetDraw,
    protocol: ImageProtocol,
    image_id: int,
    *,
    sixel_frame_fn: Callable[[Path, Path, int], Path] | None,
) -> tuple[AmbientPetPayload, str | bytes]:
    try:
        if protocol is ImageProtocol.KITTY:
            return (
                AmbientPetPayload.Text,
                image_protocol.kitty_transmit_png_with_id(request.frame, request.columns, request.rows, image_id),
            )
        if protocol is ImageProtocol.KITTY_LOCAL_FILE:
            return (
                AmbientPetPayload.Text,
                image_protocol.kitty_transmit_png_file_with_id(request.frame, request.columns, request.rows, image_id),
            )
        resolver = sixel_frame_fn or image_protocol.sixel_frame
        sixel_path = resolver(request.frame, request.sixel_dir, request.height_px)
        return (AmbientPetPayload.Bytes, Path(sixel_path).read_bytes())
    except Exception as exc:
        raise PetImageRenderError.asset(exc) from exc


def _coerce_protocol(protocol: ImageProtocol | str) -> ImageProtocol:
    if isinstance(protocol, ImageProtocol):
        return protocol
    normalized = str(protocol)
    for candidate in ImageProtocol:
        if normalized in {candidate.value, candidate.name, str(candidate)}:
            return candidate
    raise ValueError(f"unknown image protocol {protocol}")


def _move_to(x: int, y: int) -> str:
    return f"\x1b[{int(y) + 1};{int(x) + 1}H"


def _write(writer: Any, data: str | bytes) -> None:
    if isinstance(data, str):
        try:
            writer.write(data)
            return
        except TypeError:
            writer.write(data.encode())
            return
    try:
        writer.write(data)
    except TypeError:
        writer.write(data.decode("utf-8"))


def _flush(writer: Any) -> None:
    flush = getattr(writer, "flush", None)
    if flush is not None:
        flush()


__all__ = [
    "AMBIENT_PET_IMAGE_ID",
    "AmbientPet",
    "AmbientPetDraw",
    "AmbientPetPayload",
    "DEFAULT_PET_ID",
    "DISABLED_PET_ID",
    "ImageProtocol",
    "PET_PICKER_PREVIEW_IMAGE_ID",
    "PET_PICKER_VIEW_ID",
    "PetImageRenderError",
    "PetImageRenderState",
    "PetImageSupport",
    "PetImageUnsupportedReason",
    "PetNotificationKind",
    "PetPickerPreviewState",
    "RUST_MODULE",
    "SixelClearArea",
    "build_pet_picker_params",
    "builtin_spritesheet_path",
    "clear_sixel_area",
    "detect_pet_image_support",
    "ensure_builtin_pack_for_pet",
    "is_kitty_protocol",
    "render_ambient_pet_image",
    "render_pet_image",
    "render_pet_picker_preview_image",
    "test_ambient_pet",
    "write_test_pack",
]

builtin_spritesheet_path = asset_pack.builtin_spritesheet_path
write_test_pack = asset_pack.write_test_pack
detect_pet_image_support = image_protocol.detect_pet_image_support
