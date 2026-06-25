from __future__ import annotations

from pycodex.tui.exec_cell.model import CommandOutput, ExecCall, ExecCell, UNIFIED_EXEC_INTERACTION, USER_SHELL
from pycodex.tui.exec_cell.render import (
    OutputLinesParams,
    TRANSCRIPT_HINT,
    command_display_lines,
    format_unified_exec_interaction,
    new_active_exec_command,
    output_lines,
    render_line_text,
    summarize_interaction_input,
)
from pycodex.tui.line_truncation import Line, Span


def test_output_lines_ellipsis_includes_transcript_hint_matches_rust() -> None:
    # Rust: output_lines_ellipsis_includes_transcript_hint.
    output = CommandOutput(exit_code=0, aggregated_output="\n".join(str(n) for n in range(1, 8)))

    rendered = [render_line_text(line) for line in output_lines(output, OutputLinesParams(line_limit=2, include_prefix=False)).lines]

    assert any(f"...+3 lines ({TRANSCRIPT_HINT})" in line for line in rendered)


def test_command_truncation_ellipsis_does_not_include_transcript_hint_matches_rust() -> None:
    # Rust: command_truncation_ellipsis_does_not_include_transcript_hint.
    truncated = ExecCell.limit_lines_from_start([Line.from_text("first"), Line.from_text("second"), Line.from_text("third")], 2)
    assert [render_line_text(line) for line in truncated] == ["first", "second", "...+1 lines"]


def test_truncate_lines_middle_keeps_omitted_count_in_line_units_matches_rust() -> None:
    # Rust: truncate_lines_middle_keeps_omitted_count_in_line_units.
    lines = [
        Line.from_text("  ┃short"),
        Line.from_text("    this-is-a-very-long-token-that-wraps-many-rows"),
        Line.from_text(f"    {ExecCell.output_ellipsis_text(4)}"),
        Line.from_text("    tail"),
    ]

    truncated = ExecCell.truncate_lines_middle(lines, max_rows=2, width=80, omitted_hint=4, ellipsis_prefix=Line.from_spans([Span("    ")]))
    assert any(f"...+6 lines ({TRANSCRIPT_HINT})" in render_line_text(line) for line in truncated)


def test_truncate_lines_middle_does_not_truncate_blank_prefixed_output_lines_matches_rust() -> None:
    # Rust: truncate_lines_middle_does_not_truncate_blank_prefixed_output_lines.
    lines = [Line.from_text("  ┃start"), *[Line.from_text("    ") for _ in range(26)], Line.from_text("    end")]
    assert ExecCell.truncate_lines_middle(lines, max_rows=28, width=80) == lines


def test_active_command_without_animations_is_stable_matches_rust() -> None:
    # Rust: active_command_without_animations_is_stable.
    cell = new_active_exec_command("call-id", ["bash", "-lc", "echo done"], [], "Agent", None, animations_enabled=False)
    first = [render_line_text(line) for line in command_display_lines(cell, 80)]
    second = [render_line_text(line) for line in command_display_lines(cell, 80)]

    assert first == second
    assert first == ["• Running echo done"]


def test_command_display_does_not_split_long_url_token_matches_rust() -> None:
    # Rust: command_display_does_not_split_long_url_token.
    url = "http://example.com/long-url-with-dashes-wider-than-terminal-window/blah-blah-blah-text/more-gibberish-text"
    cell = new_active_exec_command("call-id", ["bash", "-lc", f"echo {url}"], [], USER_SHELL, None, False)

    rendered = [render_line_text(line) for line in command_display_lines(cell, 36)]

    assert sum(1 for line in rendered if url in line) == 1


def test_exploring_display_does_not_split_long_url_like_search_query_matches_rust() -> None:
    # Rust: exploring_display_does_not_split_long_url_like_search_query.
    url_like = "example.test/api/v1/projects/alpha-team/releases/2026-02-17/builds/1234567890/artifacts/reports/performance/summary/detail/with/a/very/long/path"
    call = ExecCall(
        call_id="call-id",
        command=["bash", "-lc", "rg foo"],
        parsed=[{"kind": "Search", "cmd": f"rg {url_like}", "query": url_like, "path": None}],
        source="Agent",
    )
    cell = ExecCell.new(call, False)

    rendered = [render_line_text(line) for line in cell.display_lines(36)]

    assert sum(1 for line in rendered if url_like in line) == 1


def test_output_display_does_not_split_long_url_like_token_without_scheme_matches_rust() -> None:
    # Rust: output_display_does_not_split_long_url_like_token_without_scheme.
    url = "example.test/api/v1/projects/alpha-team/releases/2026-02-17/builds/1234567890/artifacts/reports/performance/summary/detail/session_id=abc123def456ghi789jkl012mno345pqr678"
    call = ExecCall(
        call_id="call-id",
        command=["bash", "-lc", "echo done"],
        parsed=[],
        output=CommandOutput(exit_code=0, aggregated_output=url, formatted_output=""),
        source=USER_SHELL,
    )
    cell = ExecCell.new(call, False)

    rendered = [render_line_text(line) for line in command_display_lines(cell, 36)]

    assert sum(1 for line in rendered if url in line) == 1


def test_desired_transcript_height_accounts_for_wrapped_url_like_rows_matches_rust() -> None:
    # Rust: desired_transcript_height_accounts_for_wrapped_url_like_rows.
    url = "https://example.test/api/v1/projects/alpha-team/releases/2026-02-17/builds/1234567890/artifacts/reports/performance/summary/detail/with/a/very/long/path/that/keeps/going/for/testing/purposes"
    call = ExecCall(
        call_id="call-id",
        command=["bash", "-lc", "echo done"],
        parsed=[],
        output=CommandOutput(exit_code=0, aggregated_output=url, formatted_output=url),
        source="Agent",
        duration=1.0,
    )
    cell = ExecCell.new(call, False)
    width = 36

    assert cell.desired_transcript_height(width) > len(cell.transcript_lines(width))


def test_unified_exec_interaction_summary_and_preview_semantics() -> None:
    assert summarize_interaction_input("a`b\nc") == "a\\`b\\nc"
    assert summarize_interaction_input("x" * 81) == "x" * 80 + "..."
    assert format_unified_exec_interaction(["bash", "-lc", "cat"], "hello") == "Interacted with `cat`, sent `hello`"
    assert format_unified_exec_interaction(["bash", "-lc", "cat"], None) == "Waited for `cat`"


def test_user_shell_output_is_limited_by_screen_lines_slice() -> None:
    # Rust: user_shell_output_is_limited_by_screen_lines. Python approximates row accounting semantically.
    long_url_like = "https://example.test/api/v1/projects/" + "very-long-segment-" * 120
    output = CommandOutput(exit_code=0, aggregated_output=f"{long_url_like}\n{long_url_like}\n")
    call = ExecCall("call-id", ["bash", "-lc", "echo long"], [], output=output, source=USER_SHELL)
    cell = ExecCell.new(call, False)

    rendered = command_display_lines(cell, 20)
    output_rows = sum(1 for line in rendered if render_line_text(line).startswith(("  ┃", "    ")))

    assert output_rows <= 50
    assert any("...+" in render_line_text(line) and TRANSCRIPT_HINT in render_line_text(line) for line in rendered)
