from __future__ import annotations

import pytest

from pycodex.tui.pets.sixel import encode_rgba


EXPECTED_TRANSPARENT_BACKGROUND_DCS = "\x1bP9;1;0q"


def test_encodes_red_pixel_with_palette_and_pixel_data() -> None:
    sixel = encode_rgba(bytes([255, 0, 0, 255]), 1, 1).decode()

    assert sixel == (
        f'{EXPECTED_TRANSPARENT_BACKGROUND_DCS}"1;1;1;1#224;2;100;0;0#224@\x1b\\'
    )


def test_transparent_pixels_do_not_emit_palette_or_pixel_data() -> None:
    sixel = encode_rgba(bytes([255, 0, 0, 0]), 1, 1).decode()

    assert sixel == f'{EXPECTED_TRANSPARENT_BACKGROUND_DCS}"1;1;1;1\x1b\\'


def test_multi_band_images_advance_to_next_sixel_band() -> None:
    rgba = bytes([255, 0, 0, 255] * 7)

    sixel = encode_rgba(rgba, 1, 7).decode()

    assert sixel == (
        f'{EXPECTED_TRANSPARENT_BACKGROUND_DCS}"1;1;1;7'
        "#224;2;100;0;0#224~$-#224@\x1b\\"
    )


def test_repeated_cells_use_sixel_run_length_encoding() -> None:
    rgba = bytes([255, 0, 0, 255] * 4)

    sixel = encode_rgba(rgba, 4, 1).decode()

    assert "#224!4@" in sixel


def test_rejects_mismatched_rgba_buffer_length() -> None:
    with pytest.raises(ValueError) as excinfo:
        encode_rgba(bytes([255, 0, 0]), 1, 1)

    assert str(excinfo.value) == "sixel RGBA buffer has 3 bytes, expected 4"
