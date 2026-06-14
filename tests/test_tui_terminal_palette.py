from pycodex.tui.terminal_palette import Color
from pycodex.tui.terminal_palette import DefaultColors
from pycodex.tui.terminal_palette import StdoutColorLevel
from pycodex.tui.terminal_palette import XTERM_COLORS
from pycodex.tui.terminal_palette import best_color
from pycodex.tui.terminal_palette import default_bg
from pycodex.tui.terminal_palette import default_fg
from pycodex.tui.terminal_palette import indexed_color
from pycodex.tui.terminal_palette import rgb_color
from pycodex.tui.terminal_palette import set_default_colors_from_startup_probe
from pycodex.tui.terminal_palette import stdout_color_level
from pycodex.tui.terminal_palette import xterm_fixed_colors


def test_rgb_and_indexed_color_preserve_semantics() -> None:
    # Rust: codex-rs/tui/src/terminal_palette.rs::rgb_color / indexed_color
    assert rgb_color((1, 2, 3)) == Color("rgb", (1, 2, 3))
    assert indexed_color(42) == Color("indexed", 42)


def test_xterm_fixed_colors_skip_theme_dependent_first_sixteen() -> None:
    # Rust: codex-rs/tui/src/terminal_palette.rs::xterm_fixed_colors
    fixed = list(xterm_fixed_colors())
    assert fixed[0] == (16, XTERM_COLORS[16])
    assert fixed[-1] == (255, XTERM_COLORS[255])
    assert len(fixed) == 240


def test_best_color_truecolor_and_unknown_paths() -> None:
    # Rust: codex-rs/tui/src/terminal_palette.rs::best_color
    assert best_color((1, 2, 3), StdoutColorLevel.TRUE_COLOR) == rgb_color((1, 2, 3))
    assert best_color((1, 2, 3), StdoutColorLevel.ANSI16) == Color.default()
    assert best_color((1, 2, 3), StdoutColorLevel.UNKNOWN) == Color.default()


def test_best_color_ansi256_selects_exact_fixed_color() -> None:
    # Rust picks the xterm fixed color with minimum perceptual distance.
    assert best_color(XTERM_COLORS[24], StdoutColorLevel.ANSI256) == indexed_color(24)


def test_best_color_ansi256_never_selects_theme_dependent_system_colors() -> None:
    # Rust: best_color searches xterm_fixed_colors(), which skips indices 0..16.
    selected = best_color(XTERM_COLORS[9], StdoutColorLevel.ANSI256)

    assert selected.kind == "indexed"
    assert isinstance(selected.value, int)
    assert selected.value >= 16


def test_default_colors_can_be_seeded_from_startup_probe() -> None:
    # Rust unix path can seed the cache from terminal startup probe colors.
    set_default_colors_from_startup_probe(DefaultColors(fg=(1, 2, 3), bg=(4, 5, 6)))
    assert default_fg() == (1, 2, 3)
    assert default_bg() == (4, 5, 6)
    set_default_colors_from_startup_probe(None)
    assert default_fg() is None
    assert default_bg() is None


def test_default_colors_can_be_seeded_from_startup_probe_facade() -> None:
    # Rust maps terminal_probe::DefaultColors into terminal_palette::DefaultColors by fg/bg fields.
    probe_colors = type("ProbeDefaultColors", (), {"fg": (7, 8, 9), "bg": (10, 11, 12)})()

    set_default_colors_from_startup_probe(probe_colors)

    assert default_fg() == (7, 8, 9)
    assert default_bg() == (10, 11, 12)
    set_default_colors_from_startup_probe(None)
    assert default_fg() is None
    assert default_bg() is None


def test_stdout_color_level_uses_environment_approximation(monkeypatch) -> None:
    # Python semantic boundary for Rust supports_color::on_cached(stdout).
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.setenv("TERM", "")
    assert stdout_color_level() is StdoutColorLevel.TRUE_COLOR

    monkeypatch.setenv("COLORTERM", "")
    monkeypatch.setenv("TERM", "xterm-256color")
    assert stdout_color_level() is StdoutColorLevel.ANSI256

    monkeypatch.setenv("TERM", "xterm")
    assert stdout_color_level() is StdoutColorLevel.ANSI16

    monkeypatch.setenv("TERM", "")
    assert stdout_color_level() is StdoutColorLevel.UNKNOWN


def test_indexed_color_rejects_out_of_u8_range() -> None:
    try:
        indexed_color(256)
    except ValueError as exc:
        assert "u8" in str(exc)
    else:
        raise AssertionError("expected ValueError for out-of-range u8 color index")


def test_rgb_color_rejects_out_of_u8_channels() -> None:
    # Rust: rgb_color accepts a tuple of u8 channels; Python enforces that boundary explicitly.
    for rgb in [(-1, 0, 0), (0, 256, 0)]:
        try:
            rgb_color(rgb)
        except ValueError as exc:
            assert "u8" in str(exc)
        else:
            raise AssertionError("expected ValueError for out-of-range u8 channel")
