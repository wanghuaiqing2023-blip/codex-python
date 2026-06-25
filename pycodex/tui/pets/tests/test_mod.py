"""Parity tests for ``codex-tui/src/pets/mod.rs``."""

from __future__ import annotations

from io import BytesIO, StringIO
from pathlib import Path

import pytest

from pycodex.tui.pets import (
    AMBIENT_PET_IMAGE_ID,
    DEFAULT_PET_ID,
    DISABLED_PET_ID,
    PET_PICKER_PREVIEW_IMAGE_ID,
    PetImageRenderError,
    PetImageRenderState,
    SixelClearArea,
    clear_sixel_area,
    ensure_builtin_pack_for_pet,
    is_kitty_protocol,
    render_ambient_pet_image,
    render_pet_image,
    render_pet_picker_preview_image,
)
from pycodex.tui.pets import asset_pack
from pycodex.tui.pets.ambient import AmbientPetDraw
from pycodex.tui.pets.image_protocol import ImageProtocol


def _draw(tmp_path, protocol=ImageProtocol.KITTY):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")
    return AmbientPetDraw(
        frame=frame,
        protocol=protocol,
        x=2,
        y=3,
        clear_top_y=3,
        columns=4,
        rows=5,
        height_px=75,
        sixel_dir=tmp_path / "sixel",
    )


def test_constants_match_rust_pet_ids_and_image_ids():
    assert DEFAULT_PET_ID == "codex"
    assert DISABLED_PET_ID == "disabled"
    assert AMBIENT_PET_IMAGE_ID == 0xC0DE
    assert PET_PICKER_PREVIEW_IMAGE_ID == 0xC0DF


def test_ensure_builtin_pack_for_pet_only_fetches_builtin(tmp_path):
    calls = []

    def ensure(home, pet):
        calls.append((Path(home), pet.id))

    ensure_builtin_pack_for_pet("dewey", tmp_path, ensure_fn=ensure)
    assert calls == [(tmp_path, "dewey")]

    ensure_builtin_pack_for_pet("custom:chefito", tmp_path, ensure_fn=ensure)
    assert calls == [(tmp_path, "dewey")]


def test_ambient_pet_image_restores_cursor_after_drawing(tmp_path):
    output = StringIO()
    state = PetImageRenderState()

    render_ambient_pet_image(output, state, _draw(tmp_path))

    text = output.getvalue()
    save = text.find("\x1b7")
    move_to = text.find("\x1b[4;3H")
    image = text.find("cG5n")
    restore = text.find("\x1b8")
    assert save != -1 and move_to != -1 and image != -1 and restore != -1
    assert save < move_to < image < restore


def test_kitty_pet_image_clear_deletes_without_moving_cursor(tmp_path):
    output = StringIO()
    state = PetImageRenderState()

    render_ambient_pet_image(output, state, _draw(tmp_path))
    output.seek(0)
    output.truncate(0)
    render_ambient_pet_image(output, state, None)

    text = output.getvalue()
    assert "Ga=d,d=I,i=49374,q=2;" in text
    assert "\x1b7" not in text
    assert "\x1b[" not in text
    assert "\x1b8" not in text


def test_kitty_local_file_pet_image_uses_file_reference_without_inline_payload(tmp_path):
    output = StringIO()
    state = PetImageRenderState()

    render_ambient_pet_image(output, state, _draw(tmp_path, ImageProtocol.KITTY_LOCAL_FILE))

    text = output.getvalue()
    assert "a=d,d=I,i=49374,q=2;" in text
    assert "\x1b[4;3H" in text
    assert "a=T,t=f,f=100,c=4,r=5,q=2,i=49374;" in text
    assert "a=T,f=100,c=4,r=5,q=2,i=49374;" not in text
    assert "\x1b8" in text


def test_pet_picker_preview_image_uses_distinct_image_id(tmp_path):
    output = StringIO()
    state = PetImageRenderState()

    render_pet_picker_preview_image(output, state, _draw(tmp_path))

    assert "a=d,d=I,i=49375,q=2;" in output.getvalue()


def test_sixel_pet_image_clears_cell_area_before_redrawing(tmp_path):
    sixel_dir = tmp_path / "sixel"
    sixel_dir.mkdir()
    sixel_path = sixel_dir / "frame_h75_v2.six"
    sixel_path.write_bytes(b"fake-sixel")
    output = BytesIO()
    state = PetImageRenderState()

    render_pet_image(
        output,
        state,
        AMBIENT_PET_IMAGE_ID,
        _draw(tmp_path, ImageProtocol.SIXEL),
        sixel_frame_fn=lambda frame, directory, height: sixel_path,
    )

    text = output.getvalue().decode()
    assert "\x1b[4;3H    \x1b[5;3H    \x1b[6;3H    \x1b[7;3H    \x1b[8;3H    \x1b[4;3H" in text
    assert "fake-sixel" in text
    assert "\x1b8" in text


def test_sixel_pet_image_clear_erases_last_drawn_area(tmp_path):
    sixel_dir = tmp_path / "sixel"
    sixel_dir.mkdir()
    sixel_path = sixel_dir / "frame_h75_v2.six"
    sixel_path.write_bytes(b"fake-sixel")
    output = BytesIO()
    state = PetImageRenderState()
    request = _draw(tmp_path, ImageProtocol.SIXEL)

    render_pet_image(output, state, AMBIENT_PET_IMAGE_ID, request, sixel_frame_fn=lambda *_: sixel_path)
    output.seek(0)
    output.truncate(0)
    render_ambient_pet_image(output, state, None)

    text = output.getvalue().decode()
    assert "Ga=d,d=I,i=49374,q=2;" not in text
    assert "\x1b7" in text
    assert "\x1b[4;3H    " in text
    assert "\x1b8" in text
    assert "fake-sixel" not in text


def test_missing_frame_is_an_asset_error(tmp_path):
    request = _draw(tmp_path)
    request.frame.unlink()

    with pytest.raises(PetImageRenderError) as err:
        render_ambient_pet_image(StringIO(), PetImageRenderState(), request)

    assert err.value.kind == "asset"
    assert err.value.source() is not None


def test_writer_failure_is_a_terminal_error():
    class FailingWriter:
        def write(self, _data):
            raise OSError("test writer failed")

        def flush(self):
            pass

    state = PetImageRenderState(last_protocol=ImageProtocol.KITTY)

    with pytest.raises(PetImageRenderError) as err:
        render_ambient_pet_image(FailingWriter(), state, None)

    assert err.value.kind == "terminal"
    assert err.value.source() is not None


def test_helpers_match_rust_protocol_and_clear_area_semantics():
    assert is_kitty_protocol(ImageProtocol.KITTY)
    assert is_kitty_protocol(ImageProtocol.KITTY_LOCAL_FILE)
    assert not is_kitty_protocol(ImageProtocol.SIXEL)

    output = StringIO()
    clear_sixel_area(output, SixelClearArea(x=2, clear_top_y=1, clear_bottom_y=3, columns=4))
    assert output.getvalue() == "\x1b[2;3H    \x1b[3;3H    "
