from __future__ import annotations

import base64
import struct
import zlib

from pycodex.tui.pets.image_protocol import (
    ESC,
    ST,
    ImageProtocol,
    PetImageSupport,
    PetImageUnsupportedReason,
    ProtocolSelection,
    from_str,
    encode_rgba_sixel,
    kitty_transmit_png_file_with_id,
    kitty_transmit_png_with_id,
    parse_dotted_version,
    pet_image_support_for_terminal,
    terminal_info_for_test,
    terminal_info_with_version_for_test,
    wrap_for_tmux_if_needed,
    sixel_frame,
)


def test_protocol_selection_parses_and_explicit_resolve_ignores_tmux() -> None:
    assert from_str("auto") is ProtocolSelection.AUTO
    assert from_str("kitty") is ProtocolSelection.KITTY
    assert from_str("sixel") is ProtocolSelection.SIXEL
    assert ProtocolSelection.KITTY.resolve(env={"TMUX": "session"}) == PetImageSupport.supported(
        ImageProtocol.KITTY
    )
    assert ProtocolSelection.SIXEL.resolve(env={"TMUX": "session"}) == PetImageSupport.supported(
        ImageProtocol.SIXEL
    )


def test_tmux_passthrough_wraps_and_escapes_control_sequence() -> None:
    assert wrap_for_tmux_if_needed(f"{ESC}_Gx;{ST}", env={"TMUX": "session"}) == (
        f"{ESC}Ptmux;{ESC}{ESC}_Gx;{ESC}{ESC}\\{ST}"
    )


def test_kitty_png_transmission_encodes_inline_data(tmp_path) -> None:
    path = tmp_path / "frame.png"
    path.write_bytes(b"png")

    command = kitty_transmit_png_with_id(path, 4, 3, None, env={})

    assert command.startswith(f"{ESC}_Ga=T,t=d,f=100,c=4,r=3,q=2,m=0;")
    assert "cG5n" in command
    assert command.endswith(ST)


def test_kitty_file_png_transmission_encodes_local_file_reference(tmp_path) -> None:
    path = tmp_path / "frame.png"
    path.write_bytes(b"png")
    payload = base64.b64encode(str(path.resolve()).encode()).decode("ascii")

    assert kitty_transmit_png_file_with_id(path, 4, 3, 7, env={}) == (
        f"{ESC}_Ga=T,t=f,f=100,c=4,r=3,q=2,i=7;{payload}{ST}"
    )


def test_pet_image_support_terminal_detection_order() -> None:
    assert pet_image_support_for_terminal(
        terminal_info_for_test("Ghostty", "tmux", "Ghostty", None)
    ) == PetImageSupport.unsupported(PetImageUnsupportedReason.TMUX)
    assert pet_image_support_for_terminal(
        terminal_info_with_version_for_test("Iterm2", None, "iTerm.app", "3.6.10", None)
    ) == PetImageSupport.supported(ImageProtocol.KITTY_LOCAL_FILE)
    assert pet_image_support_for_terminal(
        terminal_info_with_version_for_test("Iterm2", None, "iTerm.app", "3.5.14", None)
    ) == PetImageSupport.unsupported(PetImageUnsupportedReason.ITERM2_TOO_OLD)
    assert pet_image_support_for_terminal(
        terminal_info_for_test("Unknown", None, None, "xterm-kitty")
    ) == PetImageSupport.supported(ImageProtocol.KITTY)
    assert pet_image_support_for_terminal(
        terminal_info_for_test("Unknown", None, None, "xterm-sixel")
    ) == PetImageSupport.supported(ImageProtocol.SIXEL)


def test_parse_dotted_version_requires_simple_numeric_components() -> None:
    assert parse_dotted_version("3.6.10") == (3, 6, 10)
    assert parse_dotted_version("3.6") == (3, 6, 0)
    assert parse_dotted_version("3") == (3, 0, 0)
    assert parse_dotted_version("3.6.10.1") is None
    assert parse_dotted_version("3.6beta") is None
    assert parse_dotted_version(None) is None


def test_encode_rgba_sixel_and_sixel_frame_cache_match_rust_boundaries(tmp_path) -> None:
    sixel = encode_rgba_sixel(bytes([255, 0, 0, 255]), 1, 1)

    assert sixel.startswith("\x1bP9;1;0q\"1;1;1;1")
    assert "#224;2;100;0;0" in sixel
    assert "#224@" in sixel
    assert sixel.endswith("\x1b\\")

    frame = tmp_path / "frame.png"
    _write_png_rgba8(frame, 1, 1, bytes([255, 0, 0, 255]))
    cache = tmp_path / "cache"

    sixel_path = sixel_frame(frame, cache, 1)

    assert sixel_path == cache / "frame_h1_v2.six"
    assert sixel_path.read_text(encoding="utf-8") == sixel

    sixel_path.write_text("cached", encoding="utf-8")
    assert sixel_frame(frame, cache, 1).read_text(encoding="utf-8") == "cached"


def test_sixel_frame_rejects_non_png_frame(tmp_path) -> None:
    frame = tmp_path / "frame.webp"
    frame.write_bytes(b"not png")

    try:
        sixel_frame(frame, tmp_path / "cache", 1)
    except ValueError as error:
        assert "expected PNG" in str(error)
    else:
        raise AssertionError("expected ValueError")


def _write_png_rgba8(path, width, height, pixels):
    raw = bytearray()
    stride = width * 4
    for row in range(height):
        raw.append(0)
        raw.extend(pixels[row * stride : (row + 1) * stride])
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    png.extend(_chunk(b"IDAT", zlib.compress(bytes(raw))))
    png.extend(_chunk(b"IEND", b""))
    path.write_bytes(bytes(png))


def _chunk(kind, payload):
    crc = zlib.crc32(kind)
    crc = zlib.crc32(payload, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)
