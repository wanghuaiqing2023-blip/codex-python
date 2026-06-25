from pycodex.tui.bottom_pane.mentions_v2.footer import footer_hint_line
from pycodex.tui.bottom_pane.mentions_v2.footer import line_text
from pycodex.tui.bottom_pane.mentions_v2.footer import render_footer
from pycodex.tui.bottom_pane.mentions_v2.footer import search_mode_indicator_line
from pycodex.tui.bottom_pane.mentions_v2.footer import truncate_line_with_ellipsis_if_overflow
from pycodex.tui.bottom_pane.mentions_v2.search_mode import SearchMode


def test_footer_hint_line_matches_visible_key_copy():
    text = line_text(footer_hint_line())
    assert "Enter" in text
    assert "insert" in text
    assert "Esc" in text
    assert "close" in text
    assert "Left/Right" in text
    assert text.endswith("switch search modes")


def test_search_mode_indicator_labels_and_active_styles():
    line = search_mode_indicator_line(SearchMode.FILESYSTEM_ONLY)
    text = line_text(line)

    assert " All Results " in text
    assert "[Filesystem Only]" in text
    assert " Plugins " in text
    active = [span for span in line.spans if span.text == "[Filesystem Only]"][0]
    assert active.style == ("cyan", "bold")


def test_tools_search_mode_uses_magenta_active_style():
    line = search_mode_indicator_line(SearchMode.TOOLS)
    active = [span for span in line.spans if span.text == "[Plugins]"][0]
    assert active.style == ("magenta", "bold")


def test_render_footer_splits_left_and_right_with_gap():
    rendered = render_footer(90, search_mode=SearchMode.RESULTS)

    assert rendered.gap == 1
    assert rendered.left_width == 90 - rendered.right.width() - 1
    assert "Enter" in rendered.text
    assert "[All Results]" in rendered.text
    assert len(rendered.text) == 90


def test_render_footer_hides_right_line_when_width_too_narrow():
    rendered = render_footer(4, search_mode=SearchMode.TOOLS)

    assert "[Plugins]" not in rendered.text
    assert len(rendered.text) == 4


def test_left_footer_truncates_when_width_is_small():
    truncated = truncate_line_with_ellipsis_if_overflow(footer_hint_line(), 10)

    assert len(line_text(truncated)) <= 10
    assert line_text(truncated).endswith(".")
