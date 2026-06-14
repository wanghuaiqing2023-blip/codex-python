from pycodex.tui.style import CYAN
from pycodex.tui.style import LIGHT_BG_ACCENT_RGB
from pycodex.tui.style import Color
from pycodex.tui.style import StdoutColorLevel
from pycodex.tui.style import Style
from pycodex.tui.style import accent_style_for
from pycodex.tui.style import best_color
from pycodex.tui.style import rgb_color
from pycodex.tui.style import table_separator_style_for
from pycodex.tui.style import user_message_bg
from pycodex.tui.style import user_message_style_for
from pycodex.tui.style import proposed_plan_bg
from pycodex.tui.style import proposed_plan_style_for


def test_accent_style_uses_darker_cyan_on_light_backgrounds() -> None:
    # Rust: codex-rs/tui/src/style.rs::tests::accent_style_uses_darker_cyan_on_light_backgrounds
    style = accent_style_for((255, 255, 255))
    assert style.fg == best_color(LIGHT_BG_ACCENT_RGB)
    assert "bold" in style.modifiers


def test_accent_style_uses_cyan_on_dark_or_unknown_backgrounds() -> None:
    # Rust: codex-rs/tui/src/style.rs::tests::accent_style_uses_cyan_on_dark_or_unknown_backgrounds
    expected = Style().with_fg(CYAN).bold()
    assert accent_style_for((0, 0, 0)) == expected
    assert accent_style_for(None) == expected


def test_table_separator_blends_toward_dark_background() -> None:
    # Rust: codex-rs/tui/src/style.rs::tests::table_separator_blends_toward_dark_background
    style = table_separator_style_for((255, 255, 255), (0, 0, 0), StdoutColorLevel.TRUE_COLOR)
    assert style.fg == rgb_color((51, 51, 51))


def test_table_separator_blends_toward_light_background() -> None:
    # Rust: codex-rs/tui/src/style.rs::tests::table_separator_blends_toward_light_background
    style = table_separator_style_for((0, 0, 0), (255, 255, 255), StdoutColorLevel.TRUE_COLOR)
    assert style.fg == rgb_color((204, 204, 204))


def test_table_separator_dims_when_palette_aware_color_is_unavailable() -> None:
    # Rust: codex-rs/tui/src/style.rs::tests::table_separator_dims_when_palette_aware_color_is_unavailable
    expected = Style().dim()
    assert table_separator_style_for((255, 255, 255), (0, 0, 0), StdoutColorLevel.ANSI16) == expected
    assert table_separator_style_for(None, (0, 0, 0), StdoutColorLevel.TRUE_COLOR) == expected


def test_user_message_and_proposed_plan_backgrounds_match_rust_blends() -> None:
    # Rust: style.rs::user_message_bg/proposed_plan_bg and *_style_for behavior contract.
    assert user_message_bg((255, 255, 255)) == best_color((244, 244, 244))
    assert user_message_bg((0, 0, 0)) == best_color((30, 30, 30))
    assert proposed_plan_bg((0, 0, 0)) == user_message_bg((0, 0, 0))
    assert user_message_style_for(None) == Style()
    assert proposed_plan_style_for(None) == Style()
    assert user_message_style_for((0, 0, 0)).bg == user_message_bg((0, 0, 0))
    assert proposed_plan_style_for((255, 255, 255)).bg == proposed_plan_bg((255, 255, 255))
