from __future__ import annotations

import base64

from pycodex.tui.pets.image_protocol import (
    ESC,
    ST,
    ImageProtocol,
    PetImageSupport,
    PetImageUnsupportedReason,
    ProtocolSelection,
    from_str,
    kitty_transmit_png_file_with_id,
    kitty_transmit_png_with_id,
    parse_dotted_version,
    pet_image_support_for_terminal,
    terminal_info_for_test,
    terminal_info_with_version_for_test,
    wrap_for_tmux_if_needed,
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
