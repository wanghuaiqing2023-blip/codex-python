"""End-to-end coverage for the ``/raw`` slash command."""

from __future__ import annotations

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.support.vt_screen import VtScreen, VtStyle
from tests.e2e.tui._slash_command_common import (
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_raw_markdown_toggle_candidate,
    run_repeated_local_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e

RAW_ON = (
    "Raw output mode on: transcript text is shown for clean terminal selection."
)
RAW_OFF = "Raw output mode off: rich transcript rendering restored."
RAW_USAGE = "Usage: /raw [on|off]"
TERMINAL_ROWS = 52
TERMINAL_COLS = 150
MARKDOWN_RESPONSE = """## MD-RICH-20260801

**BOLD-TOKEN-20260801** and *ITALIC-TOKEN-20260801*

***COMBINED-TOKEN-20260801***

`INLINE-CODE-TOKEN-20260801` and [LINK-TOKEN-20260801](https://example.com/raw-e2e)

- LIST-TOKEN-20260801
1. ORDERED-TOKEN-20260801

> QUOTE-TOKEN-20260801

| Name | Value |
| --- | --- |
| TABLE-TOKEN-20260801 | 42 |

```python
def format_probe(value: int) -> str:
    return f"RAW-CODE-20260801-{value}"
```
"""


def _row_text(screen: VtScreen, row_index: int) -> str:
    return "".join(
        cell.char for cell in screen.rows[row_index] if not cell.continuation
    ).rstrip()


def _token_cells(screen: VtScreen, token: str) -> tuple[int, int, tuple[object, ...]]:
    matches: list[tuple[int, int, tuple[object, ...]]] = []
    for row_index, row in enumerate(screen.rows):
        text = _row_text(screen, row_index)
        start = text.find(token)
        while start >= 0:
            matches.append((row_index, start, tuple(row[start : start + len(token)])))
            start = text.find(token, start + len(token))
    assert len(matches) == 1, (
        f"expected one visible {token!r}, found {len(matches)} in:\n{screen.text()}"
    )
    return matches[0]


def _styles_for_token(screen: VtScreen, token: str) -> tuple[VtStyle, ...]:
    _, _, cells = _token_cells(screen, token)
    return tuple(cell.style for cell in cells)


def _assistant_region_contract(
    screen: VtScreen,
    *,
    raw: bool,
) -> tuple[tuple[str, tuple[VtStyle, ...]], ...]:
    heading_row, _, _ = _token_cells(screen, "MD-RICH-20260801")
    code_row, _, _ = _token_cells(screen, "RAW-CODE-20260801")
    end_row = code_row
    if raw:
        for row_index in range(code_row + 1, len(screen.rows)):
            if _row_text(screen, row_index).strip() == "```":
                end_row = row_index
                break
        else:
            raise AssertionError("raw Markdown closing fence is not visible")

    result: list[tuple[str, tuple[VtStyle, ...]]] = []
    for row_index in range(heading_row, end_row + 1):
        text = _row_text(screen, row_index)
        row = screen.rows[row_index]
        result.append((text, tuple(cell.style for cell in row[: len(text)])))
    return tuple(result)


def _assert_rich_markdown(screen: VtScreen, *, label: str, checkpoint: str) -> None:
    text = screen.text()
    detail = f"{label} {checkpoint} screen:\n{text}"

    for visible in (
        "• ## MD-RICH-20260801",
        "BOLD-TOKEN-20260801",
        "ITALIC-TOKEN-20260801",
        "COMBINED-TOKEN-20260801",
        "INLINE-CODE-TOKEN-20260801",
        "LINK-TOKEN-20260801",
        "- LIST-TOKEN-20260801",
        "1. ORDERED-TOKEN-20260801",
        "> QUOTE-TOKEN-20260801",
        "TABLE-TOKEN-20260801",
        "def format_probe(value: int) -> str:",
        'return f"RAW-CODE-20260801-{value}"',
    ):
        assert visible in text, f"missing rendered Markdown {visible!r}; {detail}"

    for hidden_source in (
        "**BOLD-TOKEN-20260801**",
        "*ITALIC-TOKEN-20260801*",
        "***COMBINED-TOKEN-20260801***",
        "`INLINE-CODE-TOKEN-20260801`",
        "[LINK-TOKEN-20260801](https://example.com/raw-e2e)",
        "| --- | --- |",
        "```python",
        "```\n",
    ):
        assert hidden_source not in text, (
            f"Rich mode leaked Markdown source {hidden_source!r}; {detail}"
        )

    style_failures: list[str] = []
    if not all(style.bold for style in _styles_for_token(screen, "MD-RICH-20260801")):
        style_failures.append("heading is not bold")
    if not all(style.bold for style in _styles_for_token(screen, "BOLD-TOKEN-20260801")):
        style_failures.append("strong emphasis is not bold")
    if not all(style.italic for style in _styles_for_token(screen, "ITALIC-TOKEN-20260801")):
        style_failures.append("emphasis is not italic")
    combined = _styles_for_token(screen, "COMBINED-TOKEN-20260801")
    if not all(style.bold and style.italic for style in combined):
        style_failures.append("combined emphasis is not bold plus italic")
    if not any(
        style != VtStyle()
        for style in _styles_for_token(screen, "INLINE-CODE-TOKEN-20260801")
    ):
        style_failures.append("inline code has no Rich style")
    link_destination = _styles_for_token(screen, "https://example.com/raw-e2e")
    if not any(style.fg is not None and style.underline for style in link_destination):
        style_failures.append("web link destination is not colored and underlined")
    if not any(
        style.fg is not None
        for style in _styles_for_token(screen, "QUOTE-TOKEN-20260801")
    ):
        style_failures.append("blockquote has no Rich color")
    table_header = _styles_for_token(screen, "Name")
    if not any(style.fg is not None and style.bold for style in table_header):
        style_failures.append("table header is not colored and bold")
    if not any(
        style.fg is not None
        for style in _styles_for_token(screen, "format_probe")
    ):
        style_failures.append("Python function has no syntax color")
    if not any(
        style.fg is not None
        for style in _styles_for_token(screen, "RAW-CODE-20260801")
    ):
        style_failures.append("Python string has no syntax color")
    assert not style_failures, (
        f"{label} {checkpoint} Rich Markdown style failures:\n- "
        + "\n- ".join(style_failures)
        + f"\n{detail}"
    )


def _assert_raw_markdown(screen: VtScreen, *, label: str) -> None:
    text = screen.text()
    detail = f"{label} raw-on screen:\n{text}"
    for source_line in MARKDOWN_RESPONSE.rstrip().splitlines():
        if source_line:
            assert source_line in text, (
                f"Raw mode did not expose Markdown source line {source_line!r}; {detail}"
            )
    assert "• ## MD-RICH-20260801" not in text, (
        f"Raw mode retained the Rich assistant prefix; {detail}"
    )
    assert "━━━━━━━━" not in text, f"Raw mode retained the rendered table; {detail}"

    region = _assistant_region_contract(screen, raw=True)
    for row_text, styles in region:
        for offset, style in enumerate(styles):
            if offset < len(row_text) and not row_text[offset].isspace():
                assert style == VtStyle(), (
                    "Raw Markdown source must be unstyled: "
                    f"line={row_text!r}, offset={offset}, style={style}; {detail}"
                )


def test_raw_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch parses bare/on/off/invalid forms.
    # - AppEvent::RawOutputModeChanged delegates terminal reflow to app::input.
    route = terminal_slash_command_routes()[SlashCommand.RAW]

    assert SlashCommand.RAW.command() == "raw"
    assert SlashCommand.RAW.supports_inline_args() is True
    assert SlashCommand.RAW.available_during_task() is True
    assert SlashCommand.RAW.available_in_side_conversation() is True
    assert route.category == "core"
    assert route.outcome == "effect"
    assert route.argument_form == "inline-or-bare"


def test_windows_conpty_native_and_python_raw_forms_are_local(
    tmp_path,
) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    commands = (
        ("/raw", RAW_ON),
        ("/raw off", RAW_OFF),
        ("/raw on", RAW_ON),
        ("/raw maybe", "Usage: /raw"),
    )

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_repeated_local_slash_candidate(
            command,
            label=label,
            commands_and_effects=commands,
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        assert RAW_ON in output
        assert RAW_OFF in output
        assert RAW_USAGE in output
        assert "you\n  /raw" not in output
        assert "Traceback" not in output


@pytest.fixture(scope="module")
def raw_markdown_native_pair(tmp_path_factory):
    """Real-product Rust differential for completed Markdown history.

    This ports the behavior exercised by
    ``history_cell::tests::raw_mode_toggle_transcript_snapshot`` through the
    complete composer -> model response -> slash dispatch -> transcript reflow
    path. It deliberately inspects final VT cells rather than cumulative
    stdout, so an old Rich frame cannot make a broken Raw toggle pass.
    """

    artifact_root = tmp_path_factory.mktemp("raw-markdown-native")
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)
    checkpoints: dict[str, dict[str, VtScreen]] = {}

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_raw_markdown_toggle_candidate(
            command,
            label=label,
            response_markdown=MARKDOWN_RESPONSE,
            response_ready_text="RAW-CODE-20260801",
            artifact_dir=artifact_root / label,
            rows=TERMINAL_ROWS,
            cols=TERMINAL_COLS,
            theme_name="monokai-extended",
        )
        assert request_count == 1, (
            f"{label}: the prompt should make exactly one model request; "
            "/raw on and /raw off must remain local"
        )
        assert "Traceback" not in transcript.normalized_combined(), (
            f"{label}: unexpected process error: {transcript.normalized_combined()}"
        )

        rich_before = transcript.checkpoint_cells(
            "rich-before", rows=TERMINAL_ROWS, cols=TERMINAL_COLS
        )
        raw_on = transcript.checkpoint_cells(
            "raw-on", rows=TERMINAL_ROWS, cols=TERMINAL_COLS
        )
        rich_after = transcript.checkpoint_cells(
            "rich-after", rows=TERMINAL_ROWS, cols=TERMINAL_COLS
        )
        checkpoints[label] = {
            "rich-before": rich_before,
            "raw-on": raw_on,
            "rich-after": rich_after,
        }

    return checkpoints


def test_windows_conpty_rich_markdown_text_colors_and_modifiers_match_rust(
    raw_markdown_native_pair,
) -> None:
    """Keep Rich styling independent from the separate Raw reflow failure."""

    checkpoints = raw_markdown_native_pair
    for label in ("rust", "python"):
        _assert_rich_markdown(
            checkpoints[label]["rich-before"],
            label=label,
            checkpoint="rich-before",
        )

    assert _assistant_region_contract(
        checkpoints["python"]["rich-before"], raw=False
    ) == _assistant_region_contract(
        checkpoints["rust"]["rich-before"], raw=False
    ), "Python Rich Markdown text/layout/styles differ from live Rust"


def test_windows_conpty_raw_on_exposes_unstyled_markdown_source_like_rust(
    raw_markdown_native_pair,
) -> None:
    checkpoints = raw_markdown_native_pair
    for label in ("rust", "python"):
        _assert_raw_markdown(checkpoints[label]["raw-on"], label=label)

    assert _assistant_region_contract(
        checkpoints["python"]["raw-on"], raw=True
    ) == _assistant_region_contract(
        checkpoints["rust"]["raw-on"], raw=True
    ), "Python Raw Markdown source cells differ from live Rust"


def test_windows_conpty_raw_off_restores_exact_rich_markdown_cells(
    raw_markdown_native_pair,
) -> None:
    checkpoints = raw_markdown_native_pair
    for label in ("rust", "python"):
        rich_before = checkpoints[label]["rich-before"]
        rich_after = checkpoints[label]["rich-after"]
        _assert_rich_markdown(rich_after, label=label, checkpoint="rich-after")

        assert _assistant_region_contract(
            rich_after, raw=False
        ) == _assistant_region_contract(rich_before, raw=False), (
            f"{label}: /raw off did not restore the exact pre-toggle Rich rendering"
        )

    assert _assistant_region_contract(
        checkpoints["python"]["rich-after"], raw=False
    ) == _assistant_region_contract(
        checkpoints["rust"]["rich-after"], raw=False
    ), "Python restored Rich Markdown cells differ from live Rust"
