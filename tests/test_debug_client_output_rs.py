"""Prepared parity tests for Rust ``codex-debug-client/src/output.rs``.

Pytest is deferred until the full ``codex-debug-client`` crate is functionally
complete, per the crate-level porting workflow.
"""

from __future__ import annotations

import io

from pycodex.debug_client.output import LabelColor, Output


def test_server_json_line_writes_to_configured_file() -> None:
    # Rust source: output.rs server_json_line_writes_to_configured_file.
    jsonl = io.StringIO()
    stdout = io.StringIO()
    output = Output.new(jsonl, stdout=stdout, stderr=io.StringIO(), color=False)

    output.server_json_line('{"id":1}', False)
    output.server_json_line('{"id":2}', True)

    assert jsonl.getvalue() == '{"id":1}\n{"id":2}\n'
    assert stdout.getvalue() == ""


def test_server_json_line_without_file_honors_filtered_output() -> None:
    # Rust source: server_json_line prints to stdout only when no jsonl_file and not filtered.
    stdout = io.StringIO()
    output = Output.new(None, stdout=stdout, stderr=io.StringIO(), color=False)

    output.server_json_line('{"id":1}', False)
    output.server_json_line('{"id":2}', True)

    assert stdout.getvalue() == '{"id":1}\n'


def test_prompt_is_cleared_and_redrawn_around_server_line() -> None:
    # Rust source: server_line clears visible prompt, writes stdout, then redraws prompt.
    stdout = io.StringIO()
    stderr = io.StringIO()
    output = Output.new(None, stdout=stdout, stderr=stderr, color=False)

    output.prompt("thr_1")
    output.server_line("hello")

    assert stdout.getvalue() == "hello\n"
    assert stderr.getvalue() == "(thr_1)> \n(thr_1)> "
    assert output.prompt_state.visible is True


def test_client_line_writes_stderr_and_clears_prompt_without_redraw() -> None:
    # Rust source: client_line clears prompt and writes the client message to stderr.
    stderr = io.StringIO()
    output = Output.new(None, stdout=io.StringIO(), stderr=stderr, color=False)

    output.prompt("thr_1")
    output.client_line("client message")

    assert stderr.getvalue() == "(thr_1)> \nclient message\n"
    assert output.prompt_state.visible is False


def test_set_prompt_updates_state_without_writing() -> None:
    # Rust source: set_prompt only stores prompt thread id.
    stderr = io.StringIO()
    output = Output.new(None, stdout=io.StringIO(), stderr=stderr, color=False)

    output.set_prompt("thr_2")

    assert stderr.getvalue() == ""
    assert output.prompt_state.thread_id == "thr_2"
    assert output.prompt_state.visible is False


def test_format_label_respects_color_flag_and_codes() -> None:
    # Rust source: format_label returns raw label when color is false, ANSI color otherwise.
    plain = Output.new(None, stdout=io.StringIO(), stderr=io.StringIO(), color=False)
    colored = Output.new(None, stdout=io.StringIO(), stderr=io.StringIO(), color=True)

    assert plain.format_label("assistant", LabelColor.ASSISTANT) == "assistant"
    assert colored.format_label("assistant", LabelColor.ASSISTANT) == "\x1b[32massistant\x1b[0m"
    assert colored.format_label("tool", LabelColor.TOOL) == "\x1b[36mtool\x1b[0m"
    assert colored.format_label("meta", LabelColor.TOOL_META) == "\x1b[33mmeta\x1b[0m"
    assert colored.format_label("thread", LabelColor.THREAD) == "\x1b[34mthread\x1b[0m"
