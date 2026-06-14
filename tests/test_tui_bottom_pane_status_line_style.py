from pycodex.tui.bottom_pane.status_line_style import StatusLineAccent
from pycodex.tui.bottom_pane.status_line_style import STATUS_LINE_SEPARATOR
from pycodex.tui.bottom_pane.status_line_style import line_text
from pycodex.tui.bottom_pane.status_line_style import soften_status_line_color
from pycodex.tui.bottom_pane.status_line_style import soften_rgb_channel
from pycodex.tui.bottom_pane.status_line_style import status_line_from_segments_with_resolver
from pycodex.tui.bottom_pane.status_line_style import weighted_luma
from pycodex.tui.style import Color
from pycodex.tui.style import Style


def test_status_line_separator_matches_rust_copy():
    assert STATUS_LINE_SEPARATOR == " 路 "


def test_status_line_segments_preserve_order_and_plain_text():
    line = status_line_from_segments_with_resolver(
        [
            ("ModelName", "gpt-5"),
            ("CurrentDir", "/repo"),
            ("GitBranch", "main"),
        ],
        True,
        lambda _accent: None,
    )

    assert line is not None
    assert line_text(line) == "gpt-5 路 /repo 路 main"
    assert line.spans[0].style.fg == Color.named("cyan")
    assert "dim" not in line.spans[0].style.modifiers
    assert line.spans[2].style.fg == Color.named("green")
    assert "dim" not in line.spans[2].style.modifiers
    assert line.spans[4].style.fg == Color.named("magenta")
    assert "dim" not in line.spans[4].style.modifiers


def test_status_line_segments_dim_separators_and_use_theme_styles_first():
    def resolver(accent):
        if accent is StatusLineAccent.MODEL:
            return Style().with_fg(Color.named("red"))
        return None

    line = status_line_from_segments_with_resolver(
        [
            ("ModelName", "gpt-5"),
            ("ContextUsed", "Context 12% used"),
        ],
        True,
        resolver,
    )

    assert line is not None
    assert line.spans[0].style.fg == Color.named("red")
    assert "dim" not in line.spans[0].style.modifiers
    assert "dim" in line.spans[1].style.modifiers
    assert line.spans[2].style.fg == Color.named("green")
    assert "dim" not in line.spans[2].style.modifiers


def test_status_line_segments_soften_rgb_theme_styles_without_dimming_text():
    line = status_line_from_segments_with_resolver(
        [("ModelName", "gpt-5")],
        True,
        lambda _accent: Style().with_fg(Color.rgb((255, 0, 0))),
    )

    assert line is not None
    assert line.spans[0].style.fg == Color.rgb((228, 11, 11))
    assert "dim" not in line.spans[0].style.modifiers


def test_status_line_segments_can_disable_theme_colors():
    line = status_line_from_segments_with_resolver(
        [
            ("ModelName", "gpt-5"),
            ("ContextUsed", "Context 12% used"),
        ],
        False,
        lambda _accent: Style().with_fg(Color.named("red")),
    )

    assert line is not None
    assert line_text(line) == "gpt-5 路 Context 12% used"
    assert line.spans[0].style.fg is None
    assert "dim" in line.spans[0].style.modifiers
    assert "dim" in line.spans[1].style.modifiers
    assert line.spans[2].style.fg is None
    assert "dim" in line.spans[2].style.modifiers


def test_pull_request_number_uses_link_style():
    line = status_line_from_segments_with_resolver(
        [("PullRequestNumber", "PR #20252")],
        False,
        lambda _accent: None,
    )

    assert line is not None
    assert line.spans[0].style.fg is None
    assert "dim" in line.spans[0].style.modifiers
    assert "underlined" in line.spans[0].style.modifiers


def test_status_line_segments_return_none_when_empty():
    assert status_line_from_segments_with_resolver([], True, lambda _accent: None) is None


def test_status_line_accent_mapping_covers_all_rust_items():
    assert StatusLineAccent.for_item("ModelName") is StatusLineAccent.MODEL
    assert StatusLineAccent.for_item("ModelWithReasoning") is StatusLineAccent.MODEL
    assert StatusLineAccent.for_item("CurrentDir") is StatusLineAccent.PATH
    assert StatusLineAccent.for_item("ProjectRoot") is StatusLineAccent.PATH
    assert StatusLineAccent.for_item("GitBranch") is StatusLineAccent.BRANCH
    assert StatusLineAccent.for_item("PullRequestNumber") is StatusLineAccent.BRANCH
    assert StatusLineAccent.for_item("BranchChanges") is StatusLineAccent.BRANCH
    assert StatusLineAccent.for_item("Status") is StatusLineAccent.STATE
    assert StatusLineAccent.for_item("ContextRemaining") is StatusLineAccent.USAGE
    assert StatusLineAccent.for_item("ContextUsed") is StatusLineAccent.USAGE
    assert StatusLineAccent.for_item("ContextWindowSize") is StatusLineAccent.USAGE
    assert StatusLineAccent.for_item("UsedTokens") is StatusLineAccent.USAGE
    assert StatusLineAccent.for_item("TotalInputTokens") is StatusLineAccent.USAGE
    assert StatusLineAccent.for_item("TotalOutputTokens") is StatusLineAccent.USAGE
    assert StatusLineAccent.for_item("FiveHourLimit") is StatusLineAccent.LIMIT
    assert StatusLineAccent.for_item("WeeklyLimit") is StatusLineAccent.LIMIT
    assert StatusLineAccent.for_item("CodexVersion") is StatusLineAccent.METADATA
    assert StatusLineAccent.for_item("SessionId") is StatusLineAccent.METADATA
    assert StatusLineAccent.for_item("FastMode") is StatusLineAccent.MODE
    assert StatusLineAccent.for_item("RawOutput") is StatusLineAccent.MODE
    assert StatusLineAccent.for_item("Permissions") is StatusLineAccent.MODE
    assert StatusLineAccent.for_item("ApprovalMode") is StatusLineAccent.MODE
    assert StatusLineAccent.for_item("ThreadTitle") is StatusLineAccent.THREAD
    assert StatusLineAccent.for_item("TaskProgress") is StatusLineAccent.PROGRESS


def test_color_softening_helpers_match_rust_contract():
    assert weighted_luma(255, 0, 0) == 76
    assert soften_rgb_channel(255, 76) == 228
    assert soften_status_line_color(Color.rgb((255, 0, 0))) == Color.rgb((228, 11, 11))
    assert soften_status_line_color(Color.named("LightRed")) == Color.named("Red")
    assert soften_status_line_color(Color.named("white")) == Color.named("gray")
