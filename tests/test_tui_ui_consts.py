from pycodex.tui.ui_consts import FOOTER_INDENT_COLS
from pycodex.tui.ui_consts import LIVE_PREFIX_COLS


def test_ui_layout_constants_match_rust_values() -> None:
    # Rust: codex-rs/tui/src/ui_consts.rs constants.
    assert LIVE_PREFIX_COLS == 2
    assert FOOTER_INDENT_COLS == LIVE_PREFIX_COLS
