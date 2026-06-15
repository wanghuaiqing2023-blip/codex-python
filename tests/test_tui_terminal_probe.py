"""Parity tests for Rust ``codex-tui::terminal_probe``.

Rust source: ``codex/codex-rs/tui/src/terminal_probe.rs``.
"""

from pycodex.tui.terminal_probe import (
    DefaultColors,
    KeyboardProbeState,
    Position,
    StartupKeyboardEnhancementProbe,
    StartupProbe,
    default_colors,
    find_keyboard_flags,
    find_primary_device_attributes,
    finish_startup_probe,
    parse_cursor_position,
    parse_default_colors,
    parse_keyboard_enhancement_support,
    parse_osc_color,
    parse_osc_rgb,
    read_startup_probe,
    read_until,
    set_tty_factory,
    startup,
    startup_probe_complete,
    update_startup_probe,
)


class FakeTty:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.polls = 0

    def read_available(self, buffer):
        if self.chunks:
            buffer.extend(self.chunks.pop(0))

    def poll_readable(self, timeout):
        self.polls += 1
        return bool(self.chunks)

    def write_all(self, data):
        self.written = getattr(self, "written", b"") + data


def test_parses_cursor_position_as_zero_based() -> None:
    assert parse_cursor_position(b"\x1B[20;10R") == Position(x=9, y=19)
    assert parse_cursor_position(b"\x1B[I\x1B[20;10R") == Position(x=9, y=19)
    assert parse_cursor_position(b"\x1B[0;0R") == Position(x=0, y=0)
    assert parse_cursor_position(b"\x1B[abcR\x1B[2;3R") == Position(x=2, y=1)
    assert parse_cursor_position(b"\x1B[20R") is None


def test_parses_osc_colors_with_bel_and_st() -> None:
    assert parse_osc_color(b"\x1B]10;rgb:ffff/8000/0000\x07", 10) == (255, 127, 0)
    assert parse_osc_color(b"\x1B]11;rgba:00/80/ff/ff\x1B\\", 11) == (0, 128, 255)


def test_parses_two_and_four_digit_color_components() -> None:
    assert parse_osc_rgb("rgb:00/80/ff") == (0, 128, 255)
    assert parse_osc_rgb("rgba:ffff/8000/0000/ffff") == (255, 127, 0)
    assert parse_osc_rgb("RGB:00/80/ff") == (0, 128, 255)
    assert parse_osc_rgb("rgb:0/80/ff") is None
    assert parse_osc_rgb("rgb:00/80/ff/00") is None
    assert parse_osc_rgb("hsl:00/80/ff") is None


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
    assert find_keyboard_flags(b"\x1B[?u") is None
    assert find_keyboard_flags(b"\x1B[?bad-u") is None
    assert find_primary_device_attributes(b"\x1B[?64;1;2c") is True
    assert find_primary_device_attributes(b"\x1B[?64;xc") is None


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


def test_read_until_keeps_polling_until_parser_succeeds() -> None:
    tty = FakeTty([b"noise", b"\x1B]10;rgb:eeee/eeee/eeee\x1B\\", b"\x1B]11;rgb:1111/1111/1111\x07"])

    assert read_until(tty, timeout=None, parse=parse_default_colors) == DefaultColors(
        fg=(238, 238, 238),
        bg=(17, 17, 17),
    )
    assert tty.polls == 2


def test_read_startup_probe_keeps_polling_and_finishes_supported_keyboard_on_timeout() -> None:
    tty = FakeTty([
        b"\x1B[20;10R",
        b"\x1B]10;rgb:eeee/eeee/eeee\x1B\\\x1B]11;rgb:1111/1111/1111\x07",
        b"\x1B[?7u",
    ])

    probe = read_startup_probe(tty, timeout=None, keyboard_probe=StartupKeyboardEnhancementProbe.Query)

    assert probe == StartupProbe(
        cursor_position=Position(x=9, y=19),
        default_colors=DefaultColors(fg=(238, 238, 238), bg=(17, 17, 17)),
        keyboard_enhancement_supported=True,
    )


def test_startup_and_default_colors_write_rust_query_sequences() -> None:
    color_tty = FakeTty([
        b"\x1B]10;rgb:eeee/eeee/eeee\x1B\\\x1B]11;rgb:1111/1111/1111\x07",
    ])
    set_tty_factory(lambda: color_tty)
    try:
        assert default_colors().fg == (238, 238, 238)
        assert color_tty.written == b"\x1B]10;?\x1B\\\x1B]11;?\x1B\\"

        query_tty = FakeTty([
            b"\x1B[20;10R\x1B]10;rgb:eeee/eeee/eeee\x1B\\\x1B]11;rgb:1111/1111/1111\x07\x1B[?64;1;2c",
        ])
        set_tty_factory(lambda: query_tty)
        startup(keyboard_probe=StartupKeyboardEnhancementProbe.Query)
        assert query_tty.written == b"\x1B[6n\x1B]10;?\x1B\\\x1B]11;?\x1B\\\x1B[?u\x1B[c"

        skip_tty = FakeTty([
            b"\x1B[20;10R\x1B]10;rgb:eeee/eeee/eeee\x1B\\\x1B]11;rgb:1111/1111/1111\x07",
        ])
        set_tty_factory(lambda: skip_tty)
        probe = startup(keyboard_probe=StartupKeyboardEnhancementProbe.Skip)
        assert probe.keyboard_enhancement_supported is None
        assert skip_tty.written == b"\x1B[6n\x1B]10;?\x1B\\\x1B]11;?\x1B\\"
    finally:
        set_tty_factory(None)
