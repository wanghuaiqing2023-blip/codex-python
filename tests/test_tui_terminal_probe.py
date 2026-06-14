"""Parity tests for Rust ``codex-tui::terminal_probe``.

Rust source: ``codex/codex-rs/tui/src/terminal_probe.rs``.
"""

from pycodex.tui.terminal_probe import (
    DefaultColors,
    KeyboardProbeState,
    Position,
    StartupKeyboardEnhancementProbe,
    StartupProbe,
    finish_startup_probe,
    parse_cursor_position,
    parse_default_colors,
    parse_keyboard_enhancement_support,
    parse_osc_color,
    parse_osc_rgb,
    startup_probe_complete,
    update_startup_probe,
)


def test_parses_cursor_position_as_zero_based() -> None:
    assert parse_cursor_position(b"\x1B[20;10R") == Position(x=9, y=19)
    assert parse_cursor_position(b"\x1B[I\x1B[20;10R") == Position(x=9, y=19)


def test_parses_osc_colors_with_bel_and_st() -> None:
    assert parse_osc_color(b"\x1B]10;rgb:ffff/8000/0000\x07", 10) == (255, 127, 0)
    assert parse_osc_color(b"\x1B]11;rgba:00/80/ff/ff\x1B\\", 11) == (0, 128, 255)


def test_parses_two_and_four_digit_color_components() -> None:
    assert parse_osc_rgb("rgb:00/80/ff") == (0, 128, 255)
    assert parse_osc_rgb("rgba:ffff/8000/0000/ffff") == (255, 127, 0)


def test_parses_default_colors_from_one_buffer() -> None:
    assert parse_default_colors(
        b"\x1B]10;rgb:eeee/eeee/eeee\x1B\\\x1B]11;rgb:1111/1111/1111\x07"
    ) == DefaultColors(fg=(238, 238, 238), bg=(17, 17, 17))
    assert parse_default_colors(
        b"\x1B]11;rgb:1111/1111/1111\x07\x1B]10;rgb:eeee/eeee/eeee\x1B\\"
    ) == DefaultColors(fg=(238, 238, 238), bg=(17, 17, 17))
    assert parse_default_colors(b"\x1B]10;rgb:eeee/eeee/eeee\x1B\\") is None


def test_parses_keyboard_enhancement_flags_and_pda_fallback() -> None:
    assert parse_keyboard_enhancement_support(b"\x1B[?7u") is KeyboardProbeState.Supported
    assert parse_keyboard_enhancement_support(b"\x1B[?64;1;2c") is KeyboardProbeState.UnsupportedFallback
    assert parse_keyboard_enhancement_support(b"\x1B[?64;1;2c\x1B[?7u") is KeyboardProbeState.SupportedAndFallback
    assert parse_keyboard_enhancement_support(b"\x1B[?7u\x1B[?64;1;2c") is KeyboardProbeState.SupportedAndFallback
    assert parse_keyboard_enhancement_support(b"") is KeyboardProbeState.Pending


def test_startup_probe_parses_batched_terminal_responses() -> None:
    probe = StartupProbe()
    saw_supported_keyboard = update_startup_probe(
        probe,
        False,
        b"\x1B[20;10R\x1B]11;rgb:1111/1111/1111\x07\x1B[?64;1;2c\x1B]10;rgb:eeee/eeee/eeee\x1B\\\x1B[?7u",
        StartupKeyboardEnhancementProbe.Query,
    )
    assert probe == StartupProbe(
        cursor_position=Position(x=9, y=19),
        default_colors=DefaultColors(fg=(238, 238, 238), bg=(17, 17, 17)),
        keyboard_enhancement_supported=True,
    )
    assert saw_supported_keyboard is False
    assert startup_probe_complete(probe, StartupKeyboardEnhancementProbe.Query)


def test_finish_startup_probe_promotes_seen_supported_keyboard() -> None:
    probe = StartupProbe()
    finish_startup_probe(probe, StartupKeyboardEnhancementProbe.Query, True)
    assert probe.keyboard_enhancement_supported is True

    skipped = StartupProbe()
    finish_startup_probe(skipped, StartupKeyboardEnhancementProbe.Skip, True)
    assert skipped.keyboard_enhancement_supported is None
